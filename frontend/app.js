const links = [...document.querySelectorAll("[data-whatsapp-link]")];
const phoneDisplays = [...document.querySelectorAll("[data-phone-display]")];
const qrPanel = document.querySelector(".qr-panel");
const qrImage = document.querySelector("#qr-image");
const messagePreview = document.querySelector("#start-message");
const configStatus = document.querySelector("#config-status");

function formatPhone(number) {
  const digits = String(number || "").replace(/\D/g, "");

  if (digits.startsWith("57") && digits.length === 12) {
    return `+57 ${digits.slice(2, 5)} ${digits.slice(5, 8)} ${digits.slice(8)}`;
  }

  if (digits.startsWith("1") && digits.length === 11) {
    return `+1 ${digits.slice(1, 4)} ${digits.slice(4, 7)} ${digits.slice(7)}`;
  }

  const countryLength = Math.max(1, digits.length - 10);
  const country = digits.slice(0, countryLength);
  const local = digits.slice(countryLength).replace(/(\d{3})(?=\d)/g, "$1 ");
  return digits ? `+${country} ${local}`.trim() : "Número pendiente";
}

function disableLinks(message) {
  links.forEach((link) => {
    link.href = "#whatsapp";
    link.setAttribute("aria-disabled", "true");
    link.addEventListener("click", (event) => event.preventDefault(), { once: true });
  });
  phoneDisplays.forEach((node) => { node.textContent = "Número pendiente"; });
  qrPanel?.classList.add("is-unconfigured");
  if (configStatus) configStatus.textContent = message;
}

function applyConfig(config) {
  if (messagePreview && config.startMessage) {
    messagePreview.textContent = config.startMessage;
  }

  if (!config.configured || !config.whatsappUrl || !config.whatsappNumber) {
    disableLinks("No se pudo obtener el número público. Revisa la conexión de Kapso.");
    return;
  }

  const displayNumber = formatPhone(config.whatsappNumber);
  phoneDisplays.forEach((node) => { node.textContent = displayNumber; });

  links.forEach((link) => {
    link.href = config.whatsappUrl;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.removeAttribute("aria-disabled");
  });

  if (qrImage) {
    qrImage.addEventListener("load", () => qrImage.classList.add("is-loaded"), { once: true });
    qrImage.src = `/qr/whatsapp.svg?v=${encodeURIComponent(config.whatsappNumber)}`;
  }
}

fetch("/api/public-config", { headers: { Accept: "application/json" }, cache: "no-store" })
  .then((response) => {
    if (!response.ok) throw new Error(`config ${response.status}`);
    return response.json();
  })
  .then(applyConfig)
  .catch(() => disableLinks("No fue posible cargar el número de WhatsApp."));
