import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

// PRODUCT_SPEC §4.1: every number is a `Value` and is rendered only by <ValueView> (components/value-view.tsx).
const VALUE_RULES = [
  {
    // `v={x.amount}` is allowed: in the contract some `amount` fields are themselves Values (exposure.components[]).
    selector: "JSXExpressionContainer MemberExpression[property.name='amount']:not(JSXAttribute[name.name='v'] > JSXExpressionContainer > MemberExpression)",
    message: "Do not render Value.amount directly: use <ValueView v={…} /> (PRODUCT_SPEC §4.1).",
  },
  {
    selector: "CallExpression[callee.name=/^(parseFloat|parseInt|Number)$/] > MemberExpression[property.name='amount']",
    message: "Money is a Decimal string: never convert Value.amount to a float. Format it with <ValueView>.",
  },
  {
    selector: "CallExpression[callee.name=/^(formatAmount|formatValue)$/]",
    message: "Formatting a Value outside <ValueView> bypasses the ≈ / «Недостаточно данных» rules. Use <ValueView>.",
  },
];
// In the cabinet the legacy number formatter is banned as well: it takes a float and knows nothing of Value.
const CABINET_RULES = [
  ...VALUE_RULES,
  {
    selector: "CallExpression[callee.name='rub']",
    message: "Cabinet numbers must come from a Value: use <ValueView> instead of rub().",
  },
];

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    files: ["**/*.{ts,tsx}"],
    ignores: ["components/value-view.tsx", "lib/value.ts"],
    rules: { "no-restricted-syntax": ["error", ...VALUE_RULES] },
  },
  {
    files: ["app/demo/**/*.tsx", "components/app/**/*.tsx"],
    rules: { "no-restricted-syntax": ["error", ...CABINET_RULES] },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
