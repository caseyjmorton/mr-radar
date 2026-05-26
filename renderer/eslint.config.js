const js = require('@eslint/js');

module.exports = [
  {
    ignores: ['node_modules/**'],
  },
  js.configs.recommended,
  {
    files: ['**/*.js'],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: 'commonjs',
      globals: {
        process: 'readonly',
        console: 'readonly',
        Buffer: 'readonly',
        URL: 'readonly',
        URLSearchParams: 'readonly',
        fetch: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        setInterval: 'readonly',
        clearInterval: 'readonly',
        module: 'writable',
        require: 'readonly',
        __dirname: 'readonly',
        __filename: 'readonly',
      },
    },
    rules: {
      'no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    },
  },
];
