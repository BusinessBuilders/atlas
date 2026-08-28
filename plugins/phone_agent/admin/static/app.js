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
})();
