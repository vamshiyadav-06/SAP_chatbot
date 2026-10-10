/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: '#121311',
        brand: {
          50: '#fff8f2',
          100: '#ffeedd',
          200: '#ffd8b8',
          300: '#ffbe88',
          400: '#ff9248',
          500: '#ff6200', // Logo primary electric orange
          600: '#ea5300',
          700: '#c23e00',
          800: '#9b3200',
          900: '#7a2802',
          950: '#431301',
        },
        orange: {
          400: '#ff9248',
          500: '#ff6200',
          600: '#ea5300',
          700: '#c23e00',
        },
        sap: {
          50: '#fff8f2',
          100: '#ffeedd',
          200: '#ffd8b8',
          300: '#ffbe88',
          400: '#ff9248',
          500: '#ff6200', // Re-mapped to Clyptus Logo Orange
          600: '#ea5300',
          700: '#c23e00',
          800: '#9b3200',
          900: '#7a2802',
          950: '#431301',
        },
        slate: {
          700: '#252e42',
          750: '#1e2638',
          800: '#161d2d',
          850: '#101624',
          900: '#0b101c',
          950: '#070a12',
        }
      },
      fontFamily: {
        sans: ['"DM Sans"', 'Inter', 'system-ui', 'sans-serif'],
        display: ['Manrope', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      boxShadow: {
        'brand': '0 10px 30px -10px rgba(255, 98, 0, 0.35)',
        'brand-glow': '0 0 25px rgba(255, 98, 0, 0.45)',
      }
    },
  },
  plugins: [],
}
