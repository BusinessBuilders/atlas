/* The owner dashboard's only script of its own.
 *
 * One job: a button that has been pressed has to LOOK pressed. Signing in
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
})();
