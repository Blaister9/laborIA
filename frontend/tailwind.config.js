/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: { 50:'#f0f9ff', 500:'#0ea5e9', 600:'#0284c7', 700:'#0369a1' },
        legal: { 50:'#fefce8', 500:'#eab308', 100:'#fef9c3' },
      },
    },
  },
  plugins: [],
}
