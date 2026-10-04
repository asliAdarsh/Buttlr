import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type ThemeMode = "light" | "dark" | "system";
export type Accent = "violet" | "blue" | "emerald" | "rose" | "amber";
export type Density = "comfortable" | "compact";

const THEME_KEY = "buttlr.theme";
const ACCENT_KEY = "buttlr.accent";
const DENSITY_KEY = "buttlr.density";

interface ThemeState {
  theme: ThemeMode;
  accent: Accent;
  density: Density;
  resolvedTheme: "light" | "dark";
  setTheme: (theme: ThemeMode) => void;
  setAccent: (accent: Accent) => void;
  setDensity: (density: Density) => void;
}

const ThemeContext = createContext<ThemeState | null>(null);

function readStored<T extends string>(key: string, fallback: T): T {
  const value = localStorage.getItem(key);
  return (value as T | null) ?? fallback;
}

function systemPrefersDark(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeMode>(() => readStored<ThemeMode>(THEME_KEY, "system"));
  const [accent, setAccentState] = useState<Accent>(() => readStored<Accent>(ACCENT_KEY, "violet"));
  const [density, setDensityState] = useState<Density>(() =>
    readStored<Density>(DENSITY_KEY, "comfortable"),
  );
  const [systemDark, setSystemDark] = useState(systemPrefersDark);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const listener = (event: MediaQueryListEvent) => setSystemDark(event.matches);
    media.addEventListener("change", listener);
    return () => media.removeEventListener("change", listener);
  }, []);

  const resolvedTheme: "light" | "dark" =
    theme === "system" ? (systemDark ? "dark" : "light") : theme;

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", resolvedTheme === "dark");
    root.dataset.accent = accent;
    root.dataset.density = density;
    root.style.colorScheme = resolvedTheme;
    localStorage.setItem(THEME_KEY, theme);
    localStorage.setItem(ACCENT_KEY, accent);
    localStorage.setItem(DENSITY_KEY, density);
  }, [theme, accent, density, resolvedTheme]);

  const setTheme = useCallback((next: ThemeMode) => setThemeState(next), []);
  const setAccent = useCallback((next: Accent) => setAccentState(next), []);
  const setDensity = useCallback((next: Density) => setDensityState(next), []);

  const value = useMemo<ThemeState>(
    () => ({ theme, accent, density, resolvedTheme, setTheme, setAccent, setDensity }),
    [theme, accent, density, resolvedTheme, setTheme, setAccent, setDensity],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeState {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useTheme must be used inside ThemeProvider");
  return context;
}
