use std::fs::{self, File};
use std::io::Read;
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Stdio};

use crate::domain::project::{FileExcerpt, ProjectRoot};
use crate::error::AppError;
use crate::project_access::roots::resolve_registered_root;

const MAX_READ_FILE_BYTES: u64 = 2 * 1024 * 1024;
const MAX_EXCERPT_BYTES: usize = 20 * 1024;
const MAX_EXCERPT_LINES: usize = 120;
const MAX_SEARCH_OUTPUT_BYTES: usize = 96 * 1024;
const MAX_SEARCH_QUERY_CHARS: usize = 512;
const MAX_SEARCH_RESULTS: u32 = 50;

fn resolve_project_file(
    root: &ProjectRoot,
    relative_path: &str,
) -> Result<(PathBuf, PathBuf), AppError> {
    let root_path = resolve_registered_root(&root.path)?;
    let requested = Path::new(relative_path);
    if relative_path.is_empty()
        || requested.components().any(|component| {
            matches!(
                component,
                Component::ParentDir | Component::RootDir | Component::Prefix(_)
            )
        })
    {
        return Err(AppError::PathOutsideProject);
    }

    let file_path = root_path
        .join(requested)
        .canonicalize()
        .map_err(|_| AppError::OperationFailed)?;
    if !file_path.starts_with(&root_path) {
        return Err(AppError::PathOutsideProject);
    }
    if !file_path.is_file() {
        return Err(AppError::OperationFailed);
    }
    Ok((root_path, file_path))
}

pub fn read_file(root: ProjectRoot, relative_path: String) -> Result<FileExcerpt, AppError> {
    let (root_path, file_path) = resolve_project_file(&root, &relative_path)?;
    let metadata = fs::metadata(&file_path).map_err(|_| AppError::OperationFailed)?;
    if metadata.len() > MAX_READ_FILE_BYTES {
        return Err(AppError::ProjectFileTooLarge);
    }

    let file = File::open(&file_path).map_err(|_| AppError::OperationFailed)?;
    let mut bytes = Vec::new();
    file.take(MAX_READ_FILE_BYTES + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| AppError::OperationFailed)?;
    if bytes.len() as u64 > MAX_READ_FILE_BYTES {
        return Err(AppError::ProjectFileTooLarge);
    }
    let content = String::from_utf8(bytes).map_err(|_| AppError::OperationFailed)?;
    let mut excerpt = String::new();
    for line in content.lines().take(MAX_EXCERPT_LINES) {
        if excerpt.len() + line.len() + 1 > MAX_EXCERPT_BYTES {
            break;
        }
        excerpt.push_str(line);
        excerpt.push('\n');
    }

    let relative_path = file_path
        .strip_prefix(root_path)
        .map_err(|_| AppError::PathOutsideProject)?
        .to_string_lossy()
        .into_owned();
    Ok(FileExcerpt {
        relative_path,
        start_line: 1,
        text: excerpt,
    })
}

pub fn search(root: ProjectRoot, query: String, limit: u32) -> Result<Vec<FileExcerpt>, AppError> {
    let root_path = resolve_registered_root(&root.path)?;
    let query = query.trim();
    if query.is_empty() || query.chars().count() > MAX_SEARCH_QUERY_CHARS {
        return Err(AppError::InvalidSearchQuery);
    }

    let result_limit = limit.clamp(1, MAX_SEARCH_RESULTS) as usize;
    let mut child = Command::new("rg")
        .args([
            "--line-number",
            "--no-heading",
            "--color",
            "never",
            "--max-columns",
            "500",
            "--max-columns-preview",
            "--max-filesize",
            "2M",
            "--max-count",
            "3",
            "--glob",
            "!.git/**",
            "--glob",
            "!node_modules/**",
            "--glob",
            "!target/**",
            "--glob",
            "!dist/**",
            "--glob",
            "!.venv/**",
            "--",
        ])
        .arg(query)
        .arg(&root_path)
        .current_dir(&root_path)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|_| AppError::SearchUnavailable)?;

    let stdout = child.stdout.take().ok_or(AppError::OperationFailed)?;
    let mut bounded_stdout = stdout.take((MAX_SEARCH_OUTPUT_BYTES + 1) as u64);
    let mut output = Vec::new();
    bounded_stdout
        .read_to_end(&mut output)
        .map_err(|_| AppError::OperationFailed)?;
    let truncated = output.len() > MAX_SEARCH_OUTPUT_BYTES;
    if truncated {
        let _ = child.kill();
        output.truncate(MAX_SEARCH_OUTPUT_BYTES);
    }
    let status = child.wait().map_err(|_| AppError::OperationFailed)?;
    if !status.success() && status.code() != Some(1) && !truncated {
        return Err(AppError::SearchUnavailable);
    }

    let excerpts = String::from_utf8_lossy(&output)
        .lines()
        .filter_map(|line| {
            let mut fields = line.splitn(3, ':');
            let relative_path = fields.next()?.to_owned();
            let line_number = fields.next()?.parse::<u32>().ok()?;
            let text = fields.next()?.chars().take(500).collect::<String>();
            Some(FileExcerpt {
                relative_path,
                start_line: line_number,
                text,
            })
        })
        .take(result_limit)
        .collect();
    Ok(excerpts)
}
