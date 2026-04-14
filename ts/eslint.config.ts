import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: ["node_modules/**", "dist/**"],
  },
  // Type-aware rules only — Biome handles formatting and syntactic linting
  ...tseslint.configs.strictTypeChecked.map((config) => ({
    ...config,
    files: ["src/**/*.ts"],
  })),
  {
    files: ["src/**/*.ts"],
    languageOptions: {
      parserOptions: {
        project: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // Type-aware rules — Biome cannot cover these
      "@typescript-eslint/no-floating-promises": "error",
      "@typescript-eslint/no-misused-promises": "error",
      "@typescript-eslint/await-thenable": "error",
      "@typescript-eslint/require-await": "error",
      "@typescript-eslint/no-unnecessary-type-assertion": "error",
      "@typescript-eslint/strict-boolean-expressions": [
        "error",
        {
          allowString: false,
          allowNumber: false,
          allowNullableObject: false,
          allowNullableBoolean: false,
          allowNullableString: false,
          allowNullableNumber: false,
          allowAny: false,
        },
      ],

      // Turn off rules Biome already covers (formatting / syntactic)
      "@typescript-eslint/no-extra-semi": "off",
      "@typescript-eslint/quotes": "off",
      "@typescript-eslint/semi": "off",
      "@typescript-eslint/comma-dangle": "off",
      "@typescript-eslint/indent": "off",
      "@typescript-eslint/member-delimiter-style": "off",
      "@typescript-eslint/type-annotation-spacing": "off",

      // Turn off non-type-aware rules that Biome covers
      "no-unused-vars": "off",
      "@typescript-eslint/no-unused-vars": "off",
    },
  }
);
