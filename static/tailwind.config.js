/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // askboswell.com color palette - warm stone tones
        ink: {
          700: '#44403c',
          800: '#292524',
          900: '#1c1917',
          950: '#0c0a09',
        },
        parchment: {
          50: '#fafaf9',
          100: '#f5f5f4',
          200: '#e7e5e4',
        },
        ember: {
          400: '#fb923c',
          500: '#f97316',
          600: '#ea580c',
          glow: 'rgba(249, 115, 22, 0.15)',
        },
        // Legacy aliases for existing components
        boswell: {
          bg: '#0c0a09',           // ink-950
          'bg-secondary': '#1c1917', // ink-900
          card: '#1c1917',          // ink-900
          'card-hover': '#292524',  // ink-800
          border: '#292524',        // ink-800
          'border-light': '#44403c', // ink-700
        },
      },
      fontFamily: {
        display: ['Fraunces', 'Georgia', 'serif'],
        body: ['DM Sans', 'Inter', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
      },
      boxShadow: {
        'glow': '0 0 40px rgba(249, 115, 22, 0.15), 0 0 80px rgba(249, 115, 22, 0.1)',
        'glow-sm': '0 0 20px rgba(249, 115, 22, 0.1)',
      },
      animation: {
        'fade-in': 'fadeIn 0.5s ease-out',
        'slide-up': 'slideUp 0.5s ease-out',
        'reveal': 'reveal 0.8s ease forwards',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        reveal: {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}
