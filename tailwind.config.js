/** Build: npx tailwindcss@3 -c tailwind.config.js -i tailwind/input.css -o assets/site.css --minify
 *  build.py and the JS files must emit literal class names (no f"ball-r{n}" fragments) so the
 *  scanner can see them. Ball / heat / tool classes are plain CSS in input.css and never purged. */
module.exports = {
  content: ["./build.py", "./content/**/*.html", "./assets/js/**/*.js"],
  theme: {
    extend: {
      colors: {
        ink: { DEFAULT: "#0B1033", 2: "#312E81" },
        gold: "#FBBF24",
        maxg: { DEFAULT: "#047857", dark: "#065F46" },
        six: { DEFAULT: "#1D4ED8", dark: "#1E3A8A" },
      },
      fontFamily: { display: ['"Baloo 2"', "system-ui", "sans-serif"] },
      keyframes: {
        "ball-in": { from: { transform: "translateY(-28px) rotate(-200deg) scale(.6)", opacity: "0" } },
      },
      animation: { "ball-in": "ball-in .5s cubic-bezier(.34,1.56,.64,1) both" },
    },
  },
  plugins: [],
};
