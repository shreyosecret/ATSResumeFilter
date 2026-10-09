// Render JSON Resume files with installed themes: node render.js <jobs.json>
// jobs.json: [{"theme": "jsonresume-theme-even", "resume": "path.json", "out": "path.html"}, ...]
// Prints one line per job: ok <out> | fail <theme> <reason>
const fs = require("fs");
const path = require("path");
const jobs = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
(async () => {
  for (const job of jobs) {
    try {
      let mod = require(require.resolve(job.theme, { paths: [process.cwd()] }));
      if (mod && typeof mod.render !== "function" && mod.default) mod = mod.default;
      if (!mod || typeof mod.render !== "function") throw new Error("no render()");
      const resume = JSON.parse(fs.readFileSync(job.resume, "utf8"));
      const html = await Promise.race([
        Promise.resolve(mod.render(resume)),
        new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), 20000)),
      ]);
      if (typeof html !== "string" || html.length < 200) throw new Error("empty output");
      fs.mkdirSync(path.dirname(job.out), { recursive: true });
      fs.writeFileSync(job.out, html);
      console.log("ok " + job.out);
    } catch (e) {
      console.log("fail " + job.theme + " " + String(e && e.message || e).split("\n")[0].slice(0, 160));
    }
  }
})();
