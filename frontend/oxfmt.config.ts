import base, { tailwind } from '@erakor/toolchain/oxfmt'

// The shared style comes from erakor/toolchain; only what is this repo's own goes here.
const config = {
  ...base,
  sortTailwindcss: tailwind('src/styles/index.css'),
  ignorePatterns: ['pnpm-lock.yaml', 'node_modules/'],
}

export default config
