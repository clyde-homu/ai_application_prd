"use strict";

function num(value) {
  if (value === null || value === undefined) return 0;
  const cleaned = String(value).replace(/[$,\s]/g, "");
  const n = parseFloat(cleaned);
  return Number.isFinite(n) ? n : 0;
}

function money(n) {
  return "$" + Math.round(n).toLocaleString("en-US");
}

/* ---------------- Client form ---------------- */
function initClientForm() {
  const married = document.getElementById("married");
  const client2 = document.getElementById("client2-block");

  function syncMarried() {
    if (!client2) return;
    client2.style.opacity = married.checked ? "1" : "0.5";
  }
  if (married) {
    married.addEventListener("change", syncMarried);
    syncMarried();
  }

  const body = document.getElementById("accounts-body");
  const tpl = document.getElementById("account-row-template");
  const addBtn = document.getElementById("add-account");

  if (addBtn && body && tpl) {
    addBtn.addEventListener("click", function () {
      const frag = tpl.content.cloneNode(true);
      body.appendChild(frag);
    });
  }

  if (body) {
    body.addEventListener("click", function (e) {
      const btn = e.target.closest(".btn-remove");
      if (btn) btn.closest("tr").remove();
    });
  }
}

/* ---------------- Report data-entry form ---------------- */
function initReportForm() {
  const form = document.getElementById("report-form");
  if (!form) return;

  function set(key, value) {
    const el = form.querySelector('[data-lt="' + key + '"]');
    if (el) el.textContent = money(value);
  }

  function recompute() {
    const inflow = num(getVal("inflow"));
    const outflow = num(getVal("outflow"));
    const deductibles = num(getVal("deductibles"));
    set("excess", inflow - outflow);
    set("target", 6 * outflow + deductibles);

    let c1 = 0, c2 = 0, nonret = 0, trust = 0, liab = 0;
    form.querySelectorAll(".js-balance").forEach(function (input) {
      const v = num(input.value);
      const cat = input.dataset.category;
      const owner = input.dataset.owner;
      if (cat === "retirement" && owner === "client1") c1 += v;
      else if (cat === "retirement" && owner === "client2") c2 += v;
      else if (cat === "non_retirement") nonret += v;
      else if (cat === "trust") trust += v;
      else if (cat === "liability") liab += v;
    });
    trust += num(getVal("home_value"));

    set("c1", c1);
    set("c2", c2);
    set("nonret", nonret);
    set("trust", trust);
    set("grand", c1 + c2 + nonret + trust);
    set("liab", liab);
  }

  function getVal(id) {
    const el = document.getElementById(id);
    return el ? el.value : "";
  }

  form.addEventListener("input", recompute);

  // "Use last" single-field buttons.
  form.querySelectorAll(".use-last").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const target = form.querySelector('[name="' + btn.dataset.target + '"]');
      if (target) {
        target.value = btn.dataset.value;
        recompute();
      }
    });
  });

  // "Use last quarter's values for all blanks".
  const useAll = document.getElementById("use-all-last");
  if (useAll) {
    useAll.addEventListener("click", function () {
      form.querySelectorAll("input[data-last]").forEach(function (input) {
        if (input.value.trim() === "") input.value = input.dataset.last;
      });
      recompute();
    });
  }

  recompute();
}
