import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0d0f10",
        panel: "#151819",
        line: "#282d2e",
      },
    },
  },
  plugins: [],
};

export default config;
