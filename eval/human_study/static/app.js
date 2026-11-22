const roles = ["source", "gt", "a", "b"];
const videos = Object.fromEntries(roles.map(role => [role, document.getElementById(role)]));
const watch = {};
let rater = localStorage.getItem("phycove-rater") || "";
let item = null;
let busy = false;

const el = id => document.getElementById(id);

function resetWatch() {
  for (const role of roles) {
    watch[role] = {duration: 0, max_time: 0, ended: false, play_events: 0};
  }
  updateWatchStatus();
}

function isWatched(role) {
  const state = watch[role];
  return state.ended || (state.duration > 0 && state.max_time / state.duration >= 0.9);
}

function updateWatchStatus() {
  const count = roles.filter(isWatched).length;
  el("watch-status").textContent = `Fully watched ${count}/4`;
  const ready = count === 4 && !busy;
  document.querySelectorAll(".choice").forEach(button => button.disabled = !ready);
}

for (const role of roles) {
  const video = videos[role];
  video.addEventListener("loadedmetadata", () => {
    watch[role].duration = Number.isFinite(video.duration) ? video.duration : 0;
    updateWatchStatus();
  });
  video.addEventListener("timeupdate", () => {
    watch[role].max_time = Math.max(watch[role].max_time, video.currentTime || 0);
    updateWatchStatus();
  });
  video.addEventListener("ended", () => {
    watch[role].ended = true;
    updateWatchStatus();
  });
  video.addEventListener("play", () => watch[role].play_events += 1);
}

async function api(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function showProgress(progress) {
  if (!progress) return;
  el("progress").textContent = `${progress.completed_judgments} / ${progress.target_judgments} judgments`;
}

function clearVideos() {
  for (const video of Object.values(videos)) {
    video.pause();
    video.removeAttribute("src");
    video.load();
  }
}

function renderItem(next) {
  item = next.item;
  showProgress(next.progress);
  el("instruction").textContent = item.instruction_en;
  el("event").textContent = item.timed ? `Intervention at ${item.event.toFixed(3)} s` : "Active from the start of the video";
  resetWatch();
  for (const role of roles) {
    videos[role].src = item.media[role];
    videos[role].load();
  }
  el("message").textContent = "Please watch all four videos in full first";
}

async function loadNext() {
  busy = true;
  updateWatchStatus();
  try {
    const next = await api(`/api/next?rater=${encodeURIComponent(rater)}`);
    showProgress(next.progress);
    if (next.done) {
      clearVideos();
      el("study").classList.add("hidden");
      el("finished").classList.remove("hidden");
      return;
    }
    if (next.waiting) {
      el("message").textContent = "Other annotators are working on the remaining tasks; retrying automatically shortly";
      setTimeout(loadNext, 5000);
      return;
    }
    renderItem(next);
  } catch (error) {
    el("message").textContent = error.message;
  } finally {
    busy = false;
    updateWatchStatus();
  }
}

async function submit(choice) {
  if (!item || busy) return;
  if (choice !== "technical" && !roles.every(isWatched)) {
    el("message").textContent = "Please watch all four videos in full first";
    return;
  }
  busy = true;
  updateWatchStatus();
  el("message").textContent = "Saving…";
  try {
    await api("/api/submit", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        rater,
        token: item.token,
        choice,
        client: {watch}
      })
    });
    item = null;
    clearVideos();
    await loadNext();
  } catch (error) {
    el("message").textContent = error.message;
    busy = false;
    updateWatchStatus();
  }
}

function playAll(start) {
  for (const video of Object.values(videos)) {
    const duration = Number.isFinite(video.duration) ? video.duration : Infinity;
    video.currentTime = Math.min(start, Math.max(0, duration - 0.05));
  }
  Promise.allSettled(Object.values(videos).map(video => video.play()));
}

el("start").addEventListener("click", () => {
  const value = el("rater").value.trim();
  if (value.length < 2) {
    el("login-error").textContent = "Please enter a valid annotator code";
    return;
  }
  rater = value;
  localStorage.setItem("phycove-rater", rater);
  el("login").classList.add("hidden");
  el("study").classList.remove("hidden");
  loadNext();
});

el("rater").value = rater;
el("rater").addEventListener("keydown", event => {
  if (event.key === "Enter") el("start").click();
});
el("play-all").addEventListener("click", () => playAll(0));
el("play-event").addEventListener("click", () => playAll(item ? item.event : 0));
el("pause-all").addEventListener("click", () => Object.values(videos).forEach(video => video.pause()));
el("technical").addEventListener("click", () => submit("technical"));
document.querySelectorAll(".choice").forEach(button => {
  button.addEventListener("click", () => submit(button.dataset.choice));
});
document.addEventListener("keydown", event => {
  if (event.target && ["INPUT", "TEXTAREA"].includes(event.target.tagName)) return;
  const choice = {a: "a", t: "tie", b: "b"}[event.key.toLowerCase()];
  if (choice) {
    const button = document.querySelector(`[data-choice="${choice}"]`);
    if (button && !button.disabled) submit(choice);
  }
});

