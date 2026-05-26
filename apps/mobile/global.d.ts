// Ambient module declarations so TypeScript accepts CSS imports
// used by the Expo SDK 56 web target. Metro bundles these at runtime.

declare module '*.css';

declare module '*.module.css' {
  const classes: { readonly [key: string]: string };
  export default classes;
}
