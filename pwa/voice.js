/* Dikevia voice controls: browser speech recognition + speech synthesis.
   Voice input is handled by the browser's speech service; no audio is uploaded to Dikevia's API. */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  let recognition = null;
  let speakNextAssistant = false;

  function showMessage(message) {
    const box = $("formError");
    if (box) { box.textContent = message; box.hidden = false; }
  }

  function speak(text, button) {
    if (!("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)) {
      showMessage("La lecture vocale n'est pas disponible sur ce navigateur.");
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text || "");
    utterance.lang = "fr-FR";
    utterance.rate = 1;
    if (button) {
      const label = button.textContent;
      button.textContent = "⏸ Lecture…";
      utterance.onend = utterance.onerror = () => { button.textContent = label; };
    }
    window.speechSynthesis.speak(utterance);
  }

  function decorateAssistantMessages() {
    const messages = $("messages");
    if (!messages) return;
    messages.querySelectorAll(".msg.assistant").forEach(message => {
      if (message.dataset.voiceDecorated === "1") return;
      message.dataset.voiceDecorated = "1";
      const bubble = message.querySelector(".bubble");
      if (!bubble) return;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "voice-listen";
      button.textContent = "🔊 Écouter";
      button.addEventListener("click", () => speak(bubble.textContent, button));
      message.insertBefore(button, message.querySelector(".extra") || null);
      if (speakNextAssistant) {
        speakNextAssistant = false;
        speak(bubble.textContent, button);
      }
    });
  }

  function startListening(button, status) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      showMessage("La dictée vocale n'est pas prise en charge ici. Essaie Chrome sur Android ou le micro du clavier.");
      return;
    }
    if (recognition) { recognition.stop(); return; }
    const rec = new SpeechRecognition();
    recognition = rec;
    rec.lang = "fr-FR";
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.continuous = false;
    button.classList.add("is-listening");
    button.textContent = "■";
    status.hidden = false;
    status.textContent = "Je t'écoute… parle maintenant.";
    const input = $("question");
    const form = $("form");
    rec.onresult = event => {
      const transcript = event.results?.[0]?.[0]?.transcript?.trim();
      if (!transcript) { status.textContent = "Je n'ai pas compris. Réessaie."; return; }
      input.value = transcript;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      speakNextAssistant = true;
      status.textContent = "Question reconnue. Dikevia prépare sa réponse…";
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    };
    rec.onerror = event => {
      const message = event.error === "not-allowed"
        ? "Autorise l'accès au microphone dans les paramètres du navigateur."
        : event.error === "no-speech"
          ? "Aucune voix détectée. Appuie sur le micro et réessaie."
          : "La reconnaissance vocale a échoué. Réessaie ou utilise le clavier.";
      showMessage(message);
    };
    rec.onend = () => {
      recognition = null;
      button.classList.remove("is-listening");
      button.textContent = "🎙";
      if (!document.querySelector(".typing")) status.hidden = true;
    };
    try { rec.start(); }
    catch (_) {
      recognition = null;
      button.classList.remove("is-listening");
      button.textContent = "🎙";
      status.hidden = true;
      showMessage("Impossible de démarrer le microphone. Réessaie.");
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const form = $("form");
    const send = $("btnSend");
    const status = document.createElement("div");
    status.id = "voiceStatus";
    status.className = "voice-status";
    status.setAttribute("aria-live", "polite");
    status.hidden = true;
    form.parentNode.insertBefore(status, form);

    const mic = document.createElement("button");
    mic.type = "button";
    mic.id = "btnMic";
    mic.className = "voice-mic";
    mic.textContent = "🎙";
    mic.title = "Poser une question à voix haute";
    mic.setAttribute("aria-label", "Poser une question à voix haute");
    mic.addEventListener("click", () => startListening(mic, status));
    form.insertBefore(mic, send);

    const observer = new MutationObserver(decorateAssistantMessages);
    observer.observe($("messages"), { childList: true, subtree: true });
    decorateAssistantMessages();
  });
})();
