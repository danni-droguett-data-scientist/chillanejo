import type { Config } from "tailwindcss";
import forms from "@tailwindcss/forms";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./hooks/**/*.ts",
    "./store/**/*.ts",
  ],
  theme: {
    extend: {},
  },
  plugins: [forms],
};

export default config;
