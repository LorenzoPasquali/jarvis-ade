import type { SVGProps } from "react";

export type IconName =
  | "orbit"
  | "projects"
  | "inbox"
  | "settings"
  | "arrow-right"
  | "folder"
  | "message"
  | "trash"
  | "close"
  | "check"
  | "alert"
  | "search"
  | "terminal"
  | "microphone"
  | "speaker"
  | "volume-off";

interface IconProps extends SVGProps<SVGSVGElement> {
  name: IconName;
  size?: number;
}

export function Icon({ name, size = 20, ...props }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      focusable="false"
      {...props}
    >
      {name === "orbit" && (
        <>
          <circle cx="12" cy="12" r="2.2" fill="currentColor" stroke="none" />
          <ellipse cx="12" cy="12" rx="9" ry="4.2" transform="rotate(-32 12 12)" />
          <ellipse cx="12" cy="12" rx="9" ry="4.2" transform="rotate(32 12 12)" />
        </>
      )}
      {name === "projects" && (
        <>
          <path d="M3.5 6.8h6l2 2h9v8.9a1.5 1.5 0 0 1-1.5 1.5H5a1.5 1.5 0 0 1-1.5-1.5z" />
          <path d="M3.5 9h17" />
        </>
      )}
      {name === "inbox" && (
        <>
          <path d="M4.2 5.2h15.6l1.4 9.2v3.3a1.5 1.5 0 0 1-1.5 1.5H4.3a1.5 1.5 0 0 1-1.5-1.5v-3.3z" />
          <path d="M3.1 14.1h5.1l1.4 2h4.8l1.4-2h5.1" />
        </>
      )}
      {name === "settings" && (
        <>
          <circle cx="12" cy="12" r="3.1" />
          <path d="m19.4 13.5 1.1.9-1.3 2.3-1.3-.5a7.5 7.5 0 0 1-1.6.9l-.2 1.4h-2.7l-.3-1.4a7.5 7.5 0 0 1-1.6-.9l-1.3.5-1.3-2.3 1.1-.9a7.6 7.6 0 0 1 0-1.9l-1.1-.9 1.3-2.3 1.3.5a7.5 7.5 0 0 1 1.6-.9l.3-1.4h2.7l.2 1.4a7.5 7.5 0 0 1 1.6.9l1.3-.5 1.3 2.3-1.1.9a7.6 7.6 0 0 1 0 1.9Z" transform="translate(-1.9 -1.3)" />
        </>
      )}
      {name === "arrow-right" && (
        <>
          <path d="M4.5 12h14" />
          <path d="m13 6.5 5.5 5.5-5.5 5.5" />
        </>
      )}
      {name === "folder" && (
        <>
          <path d="M4 6.5h5.5l2 2H20v8.8a1.7 1.7 0 0 1-1.7 1.7H5.7A1.7 1.7 0 0 1 4 17.3z" />
          <path d="M4 9h16" />
        </>
      )}
      {name === "search" && (
        <>
          <circle cx="10.8" cy="10.8" r="6.4" />
          <path d="m15.5 15.5 4.2 4.2" />
        </>
      )}
      {name === "terminal" && (
        <>
          <path d="m5 7 4.5 4.5L5 16" />
          <path d="M12.5 16H19" />
          <rect x="3" y="4" width="18" height="16" rx="2.2" />
        </>
      )}
      {name === "microphone" && (
        <>
          <rect x="9" y="3.5" width="6" height="11" rx="3" />
          <path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3M9 21h6" />
        </>
      )}
      {name === "speaker" && (
        <>
          <path d="M4 9v6h4l5 4V5L8 9z" />
          <path d="M16 9.2a4 4 0 0 1 0 5.6M18.8 6.6a7.7 7.7 0 0 1 0 10.8" />
        </>
      )}
      {name === "volume-off" && (
        <>
          <path d="M4 9v6h4l5 4V5L8 9z" />
          <path d="m17 9 5 6m0-6-5 6" />
        </>
      )}
      {name === "message" && (
        <>
          <path d="M20 11.5a7.7 7.7 0 0 1-8 7.5 8.6 8.6 0 0 1-3.2-.6L4 20l1.4-3.8A7.1 7.1 0 0 1 4 11.5 7.7 7.7 0 0 1 12 4a7.7 7.7 0 0 1 8 7.5Z" />
          <path d="M8.5 11.8h7" />
          <path d="M8.5 14.8h4.5" />
        </>
      )}
      {name === "trash" && (
        <>
          <path d="M4.5 7h15" />
          <path d="M9 7V4.8h6V7" />
          <path d="m6.5 7 .8 12.2h8.4L16.5 7" />
          <path d="M10 10.5v5.2M14 10.5v5.2" />
        </>
      )}
      {name === "close" && <path d="m6 6 12 12M18 6 6 18" />}
      {name === "check" && <path d="m5 12.5 4.5 4.5L19 7.5" />}
      {name === "alert" && (
        <>
          <path d="M12 3.6 21 19H3z" />
          <path d="M12 9v4.4M12 16.4h.01" />
        </>
      )}
    </svg>
  );
}
