/* The owner dashboard's only script of its own.
 *
 * Two jobs. First: a button that has been pressed has to LOOK pressed. Signing in
 * takes a moment (the access code is compared against every owner, in a
 * thread), and a button that still reads "Sign in" during that moment gets
 * pressed a second time — which is a second attempt against the lockout for
 * something the owner already did once.
 *
 * Served from this machine and loaded with a <script src>, because the page's
 * Content-Security-Policy allows no inline script and no third-party origin.
 * Everything here degrades to nothing: with JavaScript off, the form posts
 * exactly as it does now and the server does the same work.
 */
(function () {
  "use strict";

  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!form || form.nodeName !== "FORM") {
      return;
    }
    var button = form.querySelector("[data-busy-label]");
    if (!button || button.disabled) {
      return;
    }
    button.textContent = button.getAttribute("data-busy-label");
    /* Disabled on the next tick, not this one: a control disabled while the
       browser is still collecting the form's values can be left out of what
       is posted. The label above changes immediately either way. */
    window.setTimeout(function () {
      button.disabled = true;
    }, 0);
  });

  /* Second: a copy button that copies. A caller's number is the thing the
   * owner has to paste somewhere else, and "select the text carefully with
   * your mouse" is not a feature.
   *
   * It says what happened either way. A clipboard write can be refused — an
   * insecure origin, a browser policy, a permission — and a button that
   * silently did nothing while looking like it worked is exactly the kind of
   * quiet failure this dashboard was rebuilt to remove. */
  var COPIED_MS = 2000;

  function say(button, label, failed) {
    /* Only the label span is rewritten, never the button: the icon beside it
       is part of the control and has to survive saying "Copied". */
    var slot = button.querySelector("[data-copy-label]") || button;
    var original = slot.getAttribute("data-original-label");
    if (original === null) {
      original = slot.textContent;
      slot.setAttribute("data-original-label", original);
    }
    slot.textContent = label;
    button.classList.toggle("copy-failed", !!failed);
    window.setTimeout(function () {
      slot.textContent = original;
      button.classList.remove("copy-failed");
    }, COPIED_MS);
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest ? event.target.closest("[data-copy]") : null;
    if (!button) {
      return;
    }
    event.preventDefault();
    var text = button.getAttribute("data-copy") || "";
    var failed = button.getAttribute("data-failed-label") || "Could not copy";
    var done = button.getAttribute("data-copied-label") || "Copied";
    if (!navigator.clipboard || !navigator.clipboard.writeText) {
      say(button, failed, true);
      return;
    }
    navigator.clipboard.writeText(text).then(function () {
      say(button, done, false);
    }, function (error) {
      /* Loud in the console as well as on the button: this is the only place
         the reason exists. */
      window.console.error("copy refused by the browser", error);
      say(button, failed, true);
    });
  });

  /* Third: the settings screens.
   *
   * Two small jobs, both of which the page works without.
   *
   *   1. A sticky bar that appears the moment something is typed and says the
   *      change is not saved yet. Every section still has its own save button
   *      and the server does not care about this at all — with JavaScript off
   *      the bar simply never appears.
   *   2. Repeatable rows: Remove takes a line away, and a fresh empty line
   *      appears as soon as the last one is used. With JavaScript off the form
   *      still has one empty line to type into, and clearing a line and saving
   *      still removes it — which is what the hint under every row group says.
   */
  function markDirty() {
    var bar = document.getElementById("dirty-bar");
    if (bar) {
      bar.hidden = false;
    }
  }

  document.addEventListener("input", function (event) {
    if (event.target.closest("[data-dirty-watch]")) {
      markDirty();
      addBlankRow(event.target);
    }
  });

  document.addEventListener("change", function (event) {
    if (event.target.closest("[data-dirty-watch]")) {
      markDirty();
    }
  });

  /* A save that went through leaves the panel with nothing unsaved in it. Any
     other panel on the page may still be dirty, so the bar only goes away when
     no field in the page differs from what the server last sent. Simplest
     honest rule: the swap replaces the section's markup, so re-check every
     watched form for a value the browser still thinks is edited. */
  document.body.addEventListener("htmx:afterSwap", function () {
    var bar = document.getElementById("dirty-bar");
    if (!bar) {
      return;
    }
    var edited = document.querySelectorAll("[data-dirty-watch] :is(input, textarea, select)");
    for (var i = 0; i < edited.length; i++) {
      var field = edited[i];
      if (field.type === "checkbox" || field.type === "radio") {
        if (field.checked !== field.defaultChecked) {
          return;
        }
      } else if (field.value !== field.defaultValue && field.tagName !== "SELECT") {
        return;
      }
    }
    bar.hidden = true;
  });

  function addBlankRow(field) {
    var row = field.closest ? field.closest("[data-row-blank]") : null;
    if (!row || !field.value) {
      return;
    }
    var group = row.parentNode;
    var fresh = row.cloneNode(true);
    /* The one that has just been typed into stops being the blank one, and
       gets its Remove button; the copy becomes the new blank line. */
    row.removeAttribute("data-row-blank");
    var remove = row.querySelector("[data-remove-row]");
    if (remove) {
      remove.hidden = false;
    }
    var next = fresh.querySelector("input");
    if (next) {
      next.value = "";
      next.removeAttribute("id");
      var label = fresh.querySelector("label");
      if (label) {
        label.removeAttribute("for");
      }
    }
    group.appendChild(fresh);
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest ? event.target.closest("[data-remove-row]") : null;
    if (!button) {
      return;
    }
    event.preventDefault();
    var row = button.closest("[data-row]");
    var group = row ? row.parentNode : null;
    if (!row || !group) {
      return;
    }
    /* Never leave a group with nothing to type into: removing the last line
       empties it instead of taking it away. */
    if (group.querySelectorAll("[data-row]").length <= 1) {
      var only = row.querySelector("input");
      if (only) {
        only.value = "";
        only.focus();
      }
      markDirty();
      return;
    }
    row.parentNode.removeChild(row);
    markDirty();
  });

  /* Fourth: Escape closes a confirm dialog.
   *
   * The confirms (switch the model, put the settings back, bring a business
   * back) are server-rendered <dialog open> elements, on purpose: they work
   * with JavaScript off, which is the only way a page whose CSP forbids inline
   * script can offer a confirm at all. The cost is that the browser's own
   * Escape handling belongs to showModal() and never runs for them, so the one
   * key everybody presses to back out of a question did nothing.
   *
   * This does exactly what Cancel does — it follows the dialog's Cancel link,
   * which is a plain GET back to the screen behind. Nothing here is load
   * bearing: with JavaScript off the Cancel link and the Cancel button are
   * still there and still work, and a dialog without one is left alone rather
   * than half-closed. */
  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape" || event.defaultPrevented) {
      return;
    }
    var dialog = document.querySelector('dialog[open][aria-modal="true"]');
    var cancel = dialog ? dialog.querySelector("a[data-dialog-cancel][href]") : null;
    if (!cancel) {
      return;
    }
    event.preventDefault();
    cancel.click();
  });
})();
