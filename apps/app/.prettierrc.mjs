/** @type {import("prettier").Config} */
const config = {
  singleQuote: true,
  semi: true,
  trailingComma: 'es5',
  printWidth: 100,
  arrowParens: 'avoid',
  plugins: ['@ianvs/prettier-plugin-sort-imports', 'prettier-plugin-tailwindcss'],
  importOrder: [
    '^react$',
    '^react-dom(/.*)?$',
    '^next$',
    '^next/(.*)$',
    '<THIRD_PARTY_MODULES>',
    '',
    '^@/(.*)$',
    '',
    '^\\.\\./',
    '^\\./',
  ],
  tailwindStylesheet: './src/app/globals.css',
};

export default config;
