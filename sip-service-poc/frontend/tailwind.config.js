/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        background: '#0D1117',
        surface: '#161B22',
        text: {
          primary: '#E5E7EB',
        },
        accent: {
          user: '#38BDF8',
          bot: '#34D399',
          rag: '#FBBF24',
          tool: '#A78BFA',
          error: '#F87171',
        },
      },
      fontFamily: {
        sans: ['Inter', 'Manrope', 'ui-sans-serif', 'system-ui'],
        mono: ['IBM Plex Mono', 'Fira Code', 'ui-monospace', 'SFMono-Regular'],
      },
      boxShadow: {
        'glow-user': '0 0 24px rgba(56, 189, 248, 0.35)',
        'glow-bot': '0 0 24px rgba(52, 211, 153, 0.35)',
        'glow-rag': '0 0 24px rgba(251, 191, 36, 0.35)',
        'glow-tool': '0 0 24px rgba(167, 139, 250, 0.35)',
      },
      keyframes: {
        'grid-pulse': {
          '0%, 100%': { opacity: 0.25 },
          '50%': { opacity: 0.45 },
        },
        'dust-move': {
          '0%': { transform: 'translate3d(-10%, -10%, 0) scale(1)' },
          '50%': { transform: 'translate3d(10%, 10%, 0) scale(1.05)' },
          '100%': { transform: 'translate3d(-10%, -10%, 0) scale(1)' },
        },
      },
      animation: {
        'grid-pulse': 'grid-pulse 12s ease-in-out infinite',
        'dust-move': 'dust-move 20s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};
