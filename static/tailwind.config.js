/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // askboswell.com color palette
        boswell: {
          bg: '#030303',
          'bg-secondary': '#0a0a0a',
          card: '#0f0f0f',
          'card-hover': '#141414',
          border: '#1a1a1a',
          'border-light': '#2a2a2a',
        },
        ember: {
          400: '#fb923c',
          500: '#f97316',
          600: '#ea580c',
          glow: 'rgba(249, 115, 22, 0.15)',
        },
      },
      fontFamily: {
        display: ['Playfair Display', 'Georgia', 'serif'],
        body: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
      },
      boxShadow: {
        'glow': '0 0 40px rgba(249, 115, 22, 0.15), 0 0 80px rgba(249, 115, 22, 0.1)',
        'glow-sm': '0 0 20px rgba(249, 115, 22, 0.1)',
      },
      animation: {
        'fade-in': 'fadeIn 0.5s ease-out',
        'slide-up': 'slideUp 0.5s ease-out',
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
      },
    },
  },
  plugins: [],
}
