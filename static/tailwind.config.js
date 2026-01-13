/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          900: '#0f172a',
          950: '#020617',
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
        },
      },
    },
  },
  plugins: [],
}
