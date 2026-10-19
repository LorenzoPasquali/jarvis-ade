use std::io::Read;
use std::path::Path;
use std::process::{Command, Stdio};
use std::time::{SystemTime, UNIX_EPOCH};

use crate::domain::project::{GitActivity, GitAvailability, ProjectRoot, RecentCommit};
use crate::error::AppError;
use crate::project_access::roots::resolve_registered_root;

const STATUS_OUTPUT_LIMIT: usize = 48 * 1024;
const LOG_OUTPUT_LIMIT: usize = 12 * 1024;
const DIFF_OUTPUT_LIMIT: usize = 2 * 1024;
const MAX_CHANGED_PATHS: usize = 100;
const MAX_RECENT_COMMITS: usize = 5;

struct GitOutput {
    stdout: Vec<u8>,
    truncated: bool,
}

#[derive(Debug)]
enum GitCommandError {
    Unavailable,
    Failed,
}

fn run_git(root: &Path, args: &[&str], output_limit: usize) -> Result<GitOutput, GitCommandError> {
    let mut child = Command::new("git")
        .args([
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.untrackedCache=false",
        ])
        .args(args)
        .current_dir(root)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|_| GitCommandError::Unavailable)?;

    let stdout = child.stdout.take().ok_or(GitCommandError::Unavailable)?;
    let mut bounded_stdout = stdout.take((output_limit + 1) as u64);
    let mut bytes = Vec::new();
    bounded_stdout
        .read_to_end(&mut bytes)
        .map_err(|_| GitCommandError::Unavailable)?;
    let truncated = bytes.len() > output_limit;
    if truncated {
        let _ = child.kill();
    }
    let status = child.wait().map_err(|_| GitCommandError::Unavailable)?;
    if !status.success() && !truncated {
        return Err(GitCommandError::Failed);
    }
    bytes.truncate(output_limit);
    Ok(GitOutput {
        stdout: bytes,
        truncated,
    })
}

fn observed_at_unix_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis().min(u128::from(u64::MAX)) as u64)
        .unwrap_or_default()
}

fn parse_changed_paths(output: &str) -> Vec<String> {
    output
        .lines()
        .filter(|line| !line.starts_with("## ") && line.len() > 3)
        .take(MAX_CHANGED_PATHS)
        .map(|line| line[3..].to_owned())
        .collect()
}

fn parse_branch(output: &str) -> Option<String> {
    let header = output.lines().find(|line| line.starts_with("## "))?;
    let branch = header
        .trim_start_matches("## ")
        .split("...")
        .next()
        .unwrap_or_default();
    (!branch.is_empty()).then(|| branch.to_owned())
}

fn parse_commits(output: &str) -> Vec<RecentCommit> {
    output
        .lines()
        .take(MAX_RECENT_COMMITS)
        .filter_map(|line| {
            let (short_hash, subject) = line.split_once('\t')?;
            Some(RecentCommit {
                short_hash: short_hash.to_owned(),
                subject: subject.to_owned(),
            })
        })
        .collect()
}

pub fn get_activity(root: ProjectRoot) -> Result<GitActivity, AppError> {
    let root_path = resolve_registered_root(&root.path)?;
    let top_level = match run_git(&root_path, &["rev-parse", "--show-toplevel"], 4 * 1024) {
        Ok(output) => String::from_utf8_lossy(&output.stdout).trim().to_owned(),
        Err(GitCommandError::Failed) => {
            return Ok(GitActivity::unavailable(GitAvailability::NotRepository));
        }
        Err(GitCommandError::Unavailable) => {
            return Ok(GitActivity::unavailable(GitAvailability::Unavailable));
        }
    };
    let canonical_top_level = Path::new(&top_level)
        .canonicalize()
        .map_err(|_| AppError::OperationFailed)?;
    if canonical_top_level != root_path {
        return Ok(GitActivity::unavailable(
            GitAvailability::RootOutsideConfiguredFolder,
        ));
    }

    let status = match run_git(
        &root_path,
        &["status", "--short", "--branch", "--untracked-files=normal"],
        STATUS_OUTPUT_LIMIT,
    ) {
        Ok(output) => output,
        Err(_) => return Ok(GitActivity::unavailable(GitAvailability::Unavailable)),
    };
    let status_text = String::from_utf8_lossy(&status.stdout);
    let changed_paths = parse_changed_paths(&status_text);
    let branch = parse_branch(&status_text);

    let log = run_git(
        &root_path,
        &["log", "-5", "--pretty=format:%h%x09%s"],
        LOG_OUTPUT_LIMIT,
    )
    .ok();
    let diff = run_git(
        &root_path,
        &["diff", "--shortstat", "HEAD", "--"],
        DIFF_OUTPUT_LIMIT,
    )
    .ok();
    let recent_commits = log
        .as_ref()
        .map(|output| parse_commits(&String::from_utf8_lossy(&output.stdout)))
        .unwrap_or_default();
    let diff_summary = diff.and_then(|output| {
        String::from_utf8_lossy(&output.stdout)
            .lines()
            .map(str::trim)
            .find(|line| !line.is_empty())
            .map(str::to_owned)
    });
    let truncated = status.truncated
        || log.as_ref().is_some_and(|output| output.truncated)
        || changed_paths.len() == MAX_CHANGED_PATHS;

    Ok(GitActivity {
        availability: GitAvailability::Available,
        branch,
        clean: Some(changed_paths.is_empty() && !status.truncated),
        changed_paths,
        recent_commits,
        diff_summary,
        truncated,
        observed_at_unix_ms: observed_at_unix_ms(),
    })
}
