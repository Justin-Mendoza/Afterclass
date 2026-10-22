import type { CSSProperties } from "react";

type IconName =
  | "book"
  | "ask"
  | "files"
  | "shield"
  | "arrow"
  | "upload"
  | "close"
  | "plus"
  | "chevron"
  | "spark"
  | "check"
  | "stop"
  | "download"
  | "retry";
const paths: Record<IconName, string[]> = {
  book: [
    "M4 4.5C7 3 9 4 12 5.5c3-1.5 5-2.5 8-1v15c-3-1.5-5-.5-8 1-3-1.5-5-2.5-8-1z",
    "M12 5.5v15",
  ],
  ask: [
    "M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-5 4v-4a2 2 0 0 1-2-2V6a2 2 0 0 1 3-2Z",
    "M7 9h10M7 13h6",
  ],
  files: ["M6 3h8l4 4v14H6z", "M14 3v5h4M9 12h6M9 16h5"],
  shield: ["M12 2 3 6v6c0 5 9 10 9 10s9-5 9-10V6z", "m8 12 3 3 5-6"],
  arrow: ["M5 12h14m-6-6 6 6-6 6"],
  upload: ["M12 16V3m-5 5 5-5 5 5", "M4 15v6h16v-6"],
  close: ["m6 6 12 12M6 18 18 6"],
  plus: ["M12 4v16M4 12h16"],
  chevron: ["m8 5 7 7-7 7"],
  spark: ["m12 2 2.5 7.5L22 12l-7.5 2.5L12 22l-2.5-7.5L2 12l7.5-2.5z"],
  check: ["m5 12 4 4L19 6"],
  stop: ["M6 6h12v12H6z"],
  download: ["M12 3v13m-5-5 5 5 5-5", "M4 16v5h16v-5"],
  retry: ["M4 10a8 8 0 1 1 1 8", "M4 3v7h7"],
};
export function Icon({
  name,
  size = 20,
  style,
}: {
  name: IconName;
  size?: number;
  style?: CSSProperties;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.55"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={style}
    >
      {paths[name].map((d, i) => (
        <path d={d} key={i} />
      ))}
    </svg>
  );
}
