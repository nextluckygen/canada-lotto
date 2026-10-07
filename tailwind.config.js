/** Build: npx tailwindcss@3 -c tailwind.config.js -i tailwind/input.css -o assets/site.css --minify */
module.exports = {
  content: ["./build.py", "./content/**/*.html"],
  theme: { extend: {} },
  plugins: [],
};
