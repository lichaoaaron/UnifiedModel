// Allow importing plain stylesheets for their side effects (webpack handles them
// via css-loader / sass-loader). The scaffold only declares images and fonts.
declare module '*.css';
declare module '*.scss';
