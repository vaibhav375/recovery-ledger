export const money = (n: number) =>
  "₹" + Math.round(n).toLocaleString("en-IN");

export const pct = (n: number, digits = 1) => `${(n * 100).toFixed(digits)}%`;

export const titleise = (s: string) =>
  s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
