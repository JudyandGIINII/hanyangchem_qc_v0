import js from "@eslint/js";
import { FlatCompat } from "@eslint/eslintrc";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

const compat = new FlatCompat({ baseDirectory: dirname(fileURLToPath(import.meta.url)) });

const config = [
  js.configs.recommended,
  ...compat.extends("next/core-web-vitals"),
  { ignores: [".next/**", "node_modules/**"] }
];

export default config;
