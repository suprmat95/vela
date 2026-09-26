// Applica config.js alla pagina. L'unica richiesta di rete è lo script del widget ElevenLabs,
// e parte solo se l'agent id è configurato.
(function () {
  "use strict";

  const WIDGET_SRC = "https://unpkg.com/@elevenlabs/convai-widget-embed";
  const config = window.VELA_LANDING || {};

  function clean(value) {
    return typeof value === "string" ? value.trim() : "";
  }

  function hideSoon(name) {
    document.querySelector('[data-soon="' + name + '"]').hidden = true;
  }

  function selectText(node) {
    const range = document.createRange();
    range.selectNodeContents(node);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
  }

  function setUpCopy(url) {
    const code = document.getElementById("mcp-url");
    const button = document.getElementById("copy-mcp");
    if (url) code.textContent = url;
    button.hidden = false;
    button.addEventListener("click", function () {
      if (!navigator.clipboard || !window.isSecureContext) {
        selectText(code);
        return;
      }
      navigator.clipboard.writeText(code.textContent).then(function () {
        button.textContent = "Copiato";
        setTimeout(function () { button.textContent = "Copia"; }, 2000);
      }, function () {
        selectText(code);
      });
    });
  }

  function showVoice(agentId) {
    if (!agentId) return;
    const widget = document.createElement("elevenlabs-convai");
    widget.setAttribute("agent-id", agentId);
    document.getElementById("voice-widget").appendChild(widget);
    const script = document.createElement("script");
    script.src = WIDGET_SRC;
    script.async = true;
    document.body.appendChild(script);
    hideSoon("voice");
  }

  function showPhone(number) {
    const dialable = number.replace(/[^\d+]/g, "");
    if (!dialable) return;
    const link = document.getElementById("phone-link");
    link.href = "tel:" + dialable;
    link.textContent = number;
    link.hidden = false;
    hideSoon("phone");
  }

  setUpCopy(clean(config.mcpUrl));
  showVoice(clean(config.elevenLabsAgentId));
  showPhone(clean(config.phoneNumber));
})();
