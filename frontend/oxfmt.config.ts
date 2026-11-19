import base from '@erakor/toolchain/oxfmt'

// The shared style comes from erakor/toolchain; only what is this repo's own goes here.
const config = {
  ...base,
  sortTailwindcss: {
    stylesheet: 'src/styles/index.css',
    functions: ['cn', 'cva'],
  },
  ignorePatterns: ['pnpm-lock.yaml', 'node_modules/'],
}

export default config
