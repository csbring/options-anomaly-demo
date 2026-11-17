"use strict";
const $ = id => document.getElementById(id);
let reportId = null, report = null, busy = false;
function addMessage(text, user = false, label = "ANOMALY LAB", error = false) {
  const article = document.createElement("article");
  article.className = `message ${user ? "user" : "assistant"}${error ? " error" : ""}`;
  const speaker = document.createElement("span"); speaker.className = "speaker"; speaker.textContent = user ? "YOU" : label;
  const p = document.createElement("p"); p.textContent = text;
  article.append(speaker, p); $("chat").append(article);
  while ($("chat").children.length > 30) $("chat").firstElementChild.remove();
  $("chat").scrollTop = $("chat").scrollHeight;
}
function displayReport(data) {
  report = data;
  $("empty").hidden = true; $("report").hidden = false;
  $("ticker").textContent = data.symbol; $("basis").textContent = data.model_basis;
  $("mode-label").textContent = data.source === "synthetic" ? "SYNTHETIC DATA" : "TWS SNAPSHOT";
  $("provenance").textContent = `${data.source_label} · ${data.metadata.quote_time}`;
  $("quotes").textContent = data.quotes; $("flagged").textContent = data.flagged;
  $("sides").textContent = `${data.calls} / ${data.puts}`;
  $("quality").textContent = `${data.quality_pass} / ${data.flagged}`;
  $("chart").src = `data:image/png;base64,${data.chart}`;
  $("rows").replaceChildren();
  for (const row of data.rows) {
    const tr = document.createElement("tr");
    const ratio = row.volume_oi_ratio === null ? "OI missing" : `${row.volume_oi_ratio.toFixed(1)}×`;
    for (const value of [row.contract + (row.is_anomaly ? " •" : ""), `${Math.round(row.volume).toLocaleString()} / ${Math.round(row.open_interest).toLocaleString()} (${ratio})`, `${(row.spread_pct*100).toFixed(1)}%`, row.anomaly_score.toFixed(3), row.reason]) {
      const td = document.createElement("td"); td.textContent = value; tr.append(td);
    }
    $("rows").append(tr);
  }
}
async function send(message) {
  if (busy || !message.trim()) return;
  busy = true; $("send").disabled = true; $("scenario").disabled = true;
  document.querySelectorAll("[data-message]").forEach(b => b.disabled = true);
  addMessage(message, true); $("message").value = "";
  $("status").textContent = "Working through the data…";
  try {
    const response = await fetch("/api/chat", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({message, report_id: reportId, scenario: $("scenario").value})});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Check the message and try again.");
    reportId = data.report_id;
    if (data.report) displayReport(data.report);
    addMessage(data.text, false, data.narrator);
    $("status").textContent = "Ready. Ask a follow-up or enter another ticker.";
  } catch (error) {
    addMessage(error.message || "Could not reach the local server.", false, "PLEASE TRY AGAIN", true);
    $("status").textContent = "Your previous report is still available.";
  } finally {
    busy = false; $("send").disabled = false; $("scenario").disabled = false;
    document.querySelectorAll("[data-message]").forEach(b => b.disabled = false);
  }
}
$("composer").addEventListener("submit", e => {e.preventDefault(); send($("message").value);});
document.querySelectorAll("[data-message]").forEach(button => button.addEventListener("click", () => send(button.dataset.message)));
$("scenario").addEventListener("change", () => {if (report) send(report.symbol);});
function download(blob, name) {
  const url = URL.createObjectURL(blob), a = document.createElement("a");
  a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$("download-chart").addEventListener("click", () => {if (report) download(new Blob([Uint8Array.from(atob(report.chart), c => c.charCodeAt(0))], {type:"image/png"}), `${report.symbol}-anomalies.png`);});
$("download-csv").addEventListener("click", () => {if (report) download(new Blob([report.csv], {type:"text/csv"}), `${report.symbol}-quotes.csv`);});
fetch("/api/status").then(r => r.json()).then(s => {
  $("environment").textContent = s.local_model ? "LOCAL MODEL CONFIGURED" : "LOCAL RESEARCH DEMO";
  if (s.source === "tws") {
    $("mode-label").textContent = "TWS MODE";
    $("scenario").hidden = true; document.querySelector('label[for="scenario"]').hidden = true;
    $("chat").firstElementChild.querySelector("p").textContent = "TWS mode is enabled. Enter a ticker to request a bounded option snapshot from your local broker connection. The resulting report identifies live, frozen or delayed data.";
    document.querySelector(".empty-note").textContent = "TWS mode uses your configured local connection. Data availability and quality depend on subscriptions and market hours.";
  }
}).catch(() => {$("status").textContent = "Server unavailable. Restart the local demo.";});
