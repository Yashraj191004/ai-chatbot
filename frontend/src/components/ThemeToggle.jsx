import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";

const getInitialTheme = () => {
  const saved = localStorage.getItem("theme");
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
};

export default function ThemeToggle({ className = "" }) {
  const [theme, setTheme] = useState(getInitialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);

  const isLight = theme === "light";

  return (
    <button
      type="button"
      className={`theme-toggle ${className}`}
      onClick={() => setTheme(isLight ? "dark" : "light")}
      title={isLight ? "Switch to dark mode" : "Switch to light mode"}
      aria-label={isLight ? "Switch to dark mode" : "Switch to light mode"}
    >
      {isLight ? <Moon size={17} /> : <Sun size={17} />}
    </button>
  );
}
