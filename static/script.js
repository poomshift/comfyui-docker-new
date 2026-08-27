let socket;
let lastLogHash = "";
let logUpdateCounter = 0;
let isUpdating = false;
let autoScroll = true;
let userScrolled = false;
let reconnectAttempts = 0;

const maxReconnectAttempts = 5;

const sourceMapping = {
  civitai: "civitaibutton",
  huggingface: "huggingfacebutton",
  gdrive: "gdrivebutton",
};
const statusMapping = {
  civitai: "downloadStatus",
  huggingface: "hfDownloadStatus",
  gdrive: "gdDownloadStatus",
};

function generateRandomString(length) {
  const characters =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  let result = "";
  for (let i = 0; i < length; i++) {
    result += characters.charAt(Math.floor(Math.random() * characters.length));
  }

  return result;
}

var support = (function () {
  if (!window.DOMParser) return false;
  var parser = new DOMParser();
  try {
    parser.parseFromString("x", "text/html");
  } catch (err) {
    return false;
  }
  return true;
})();

/**
 * Convert a template string into HTML DOM nodes
 * @param  {String} str The template string
 * @return {Node}       The template HTML
 */
var stringToHTML = function (str) {
  // Otherwise, fallback to old-school method
  var dom = document.createElement("div");
  dom.className = "log-line";
  dom.innerHTML = str;
  return dom;
};

function initializeWebSocket() {

  // websocket connection handle here

  try {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    console.log("Connecting to WebSocket:", wsUrl);

    socket = new WebSocket(wsUrl);

    socket.onopen = function () {
      console.log("WebSocket connected");
      reconnectAttempts = 0;
    };

    socket.onmessage = function (event) {
      const msg = JSON.parse(event.data);
      if (msg.type === "new_log_line") {
        appendLogWs(msg);
      } else if (msg.type === "download") {
        const button_source = sourceMapping[msg.data.source];
        const status_source = statusMapping[msg.data.source];

        const btn = document.getElementById(button_source);
        const statusDiv = document.getElementById(status_source);

        switch (msg.data.status) {
          case "success":
            btn.disabled = false;
            statusDiv.textContent = "Download Completed";
            statusDiv.className = "status-message status-success";
            break;
          case "failed":
            btn.disabled = false;
            statusDiv.textContent = `Download Error ${msg.data.detail}`;
            statusDiv.className = "status-message status-error";
            break;
          case "downloading":
            btn.disabled = true;
            statusDiv.textContent = "Downloading...";
            statusDiv.className = "status-message";
            break;
        }
      }
    };

    socket.onclose = function () {
      console.log("WebSocket disconnected");
      // Attempt to reconnect
      if (reconnectAttempts < maxReconnectAttempts) {
        reconnectAttempts++;
        console.log(
          `Attempting to reconnect (${reconnectAttempts}/${maxReconnectAttempts})...`
        );
        setTimeout(() => initializeWebSocket(), 2000 * reconnectAttempts);
      }
    };

    socket.onerror = function () {
      startAutoPoll();
      console.error("WebSocket error:", error);
    };
  } catch (e) {
    console.error("WebSocket initialization failed:", e);
  }
}

function appendLogWs(data) {

  // append logs + scroll down and remove element when it more than 500 lines.

  const logBox = document.getElementById("log-box");
  const parsed = stringToHTML(data.line);

  // Only update if content actually changed
  isUpdating = true;

  // Save current scroll position and check if scrolled to bottom
  const wasAtBottom =
    isScrolledToBottom(logBox) || (autoScroll && !userScrolled);
  const scrollPos = logBox.scrollTop;

  // Update content with minimal flickering
  requestAnimationFrame(() => {
    logBox.style.opacity = "0.7";

    logBox.appendChild(parsed);
    // Use timeout to allow the opacity transition to happen
    setTimeout(() => {
      logBox.style.opacity = "1";

      if (logBox.childNodes.length > 500) {
        logBox.removeChild(logBox.firstChild);
      }

      // Maintain scroll position
      if (wasAtBottom) {
        scrollToBottom(logBox);
      } else {
        logBox.scrollTop = scrollPos;
      }

      isUpdating = false;
    }, 50);
  });
}

function updateLogBoxSmoothly(logs) {

  // for logs polling method.

  if (!logs || isUpdating) return;

  const logBox = document.getElementById("log-box");

  // Generate simple hash of the log content to check for changes
  const hash = generateRandomString(10);

  if (hash !== lastLogHash) {
    // Only update if content actually changed
    isUpdating = true;

    // Save current scroll position and check if scrolled to bottom
    const wasAtBottom =
      isScrolledToBottom(logBox) || (autoScroll && !userScrolled);
    const scrollPos = logBox.scrollTop;

    // Update content with minimal flickering
    requestAnimationFrame(() => {
      logBox.style.opacity = "0.7";

      // Use timeout to allow the opacity transition to happen
      setTimeout(() => {
        logBox.innerHTML = logs;
        logBox.style.opacity = "1";

        // Maintain scroll position
        if (wasAtBottom) {
          scrollToBottom(logBox);
        } else {
          logBox.scrollTop = scrollPos;
        }

        lastLogHash = hash;
        isUpdating = false;
      }, 50);
    });
  }
}

function isScrolledToBottom(element) {

  // check scroll?

  return (
    Math.abs(element.scrollHeight - element.scrollTop - element.clientHeight) <
    1
  );
}

function scrollToBottom(element) {
  
  // scroll to bottom

  element.scrollTop = element.scrollHeight;
}

function toggleAutoScroll() {

  // toggle switch

  autoScroll = !autoScroll;
  userScrolled = false;

  // If turning on auto-scroll, immediately scroll to bottom
  if (autoScroll) {
    const logBox = document.getElementById("log-box");
    scrollToBottom(logBox);
  }

  // Save preference
  localStorage.setItem("autoScroll", autoScroll ? "true" : "false");
  console.log("Auto-scroll " + (autoScroll ? "enabled" : "disabled"));
}

function fetchLatestLogs(isManualRefresh) {

  // fallback when ws is not support.

  if (isUpdating && !isManualRefresh) return;

  console.log("Fetching latest logs...");
  fetch("/logs", {
    method: "GET",
    cache: "no-cache",
    headers: {
      "Cache-Control": "no-cache",
      Pragma: "no-cache",
    },
  })
    .then((response) => response.json())
    .then((data) => {
      if (data && data.logs) {
        console.log("Latest logs received, updating display");
        updateLogBoxSmoothly(data.logs);
      } else {
        console.warn("No logs data in response");
        document.getElementById("log-box").style.opacity = "1";
      }
    })
    .catch((error) => {
      console.error("Error fetching logs:", error);
      document.getElementById("log-box").style.opacity = "1";
    });
}

// Auto-poll for logs every 3 seconds as fallback
function startAutoPoll() {
  console.log("Starting auto polling");
  setInterval(() => fetchLatestLogs(false), 3000);
}

// download from civitai website
async function downloadFromCivitai() {
  const url = document.getElementById("modelUrl").value;
  const apiKey = document.getElementById("apiKey").value;
  const modelType = document.getElementById("modelType").value;
  const statusDiv = document.getElementById("downloadStatus");

  const civitaibutton = document.getElementById("civitaibutton");

  try {
    const response = await fetch("/download/civitai", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: url,
        api_key: apiKey,
        model_type: modelType,
      }),
    });

    if (response.status === 204) {
      civitaibutton.disabled = true;

      statusDiv.className = "status-message";
      statusDiv.style.display = "block";
      statusDiv.textContent = "Downloading...";
    } else {
      const data = await response.json();

      throw { message: data.detail };
    }
  } catch (error) {
    statusDiv.textContent = "Error: " + error.message;
    statusDiv.className = "status-message status-error";
  }
}

// download from huggingface website 
async function downloadFromHuggingFace() {
  const url = document.getElementById("hfUrl").value;
  const token = document.getElementById("hfToken").value;
  const modelType = document.getElementById("hfModelType").value;
  const statusDiv = document.getElementById("hfDownloadStatus");

  const huggingfacebutton = document.getElementById("huggingfacebutton");

  try {
    const response = await fetch("/download/huggingface", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: url,
        api_key: token,
        model_type: modelType,
      }),
    });

    if (response.status === 204) {
      huggingfacebutton.disabled = true;

      statusDiv.className = "status-message";
      statusDiv.style.display = "block";
      statusDiv.textContent = "Downloading...";
    } else {
      const data = await response.json();
      throw { message: data.detail };
    }
  } catch (error) {
    statusDiv.textContent = "Error: " + error.message;
    statusDiv.className = "status-message status-error";
  }
}

// download from google drive
async function downloadFromGoogleDrive() {
  const url = document.getElementById("gdUrl").value;
  const modelType = document.getElementById("gdModelType").value;
  const filename = document.getElementById("gdFilename").value;
  const statusDiv = document.getElementById("gdDownloadStatus");

  const gdrivebutton = document.getElementById("gdrivebutton");

  try {
    const response = await fetch("/download/googledrive", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: url,
        model_type: modelType,
        filename: filename,
      }),
    });

    if (response.status === 204) {
      gdrivebutton.disabled = true;

      statusDiv.className = "status-message";
      statusDiv.style.display = "block";
      statusDiv.textContent = "Downloading...";
    } else {
      const data = await response.json();
      throw { message: data.detail };
    }
  } catch (error) {
    statusDiv.textContent = "Error: " + error.message;
    statusDiv.className = "status-message status-error";
  }
}

function switchTab(tabName) {
  // Hide all downloaders
  document.querySelectorAll(".downloader").forEach((downloader) => {
    downloader.classList.remove("active");
  });

  // Deactivate all tabs
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.classList.remove("active");
  });

  // Activate the selected tab and downloader
  document.getElementById(tabName + "-tab").classList.add("active");
  document.getElementById(tabName + "-downloader").classList.add("active");
}

document.addEventListener("DOMContentLoaded", function () {
  console.log("Page loaded, initializing systems");

  // Initialize WebSocket and fallback polling
  initializeWebSocket();

  // Initialize tabs - start with Civitai tab active
  switchTab("civitai");

  // Set up auto-scroll toggle from saved preference
  const logBox = document.getElementById("log-box");
  const savedAutoScroll = localStorage.getItem("autoScroll");
  if (savedAutoScroll !== null) {
    autoScroll = savedAutoScroll === "true";
    document.getElementById("auto-scroll-toggle").checked = autoScroll;
    scrollToBottom(logBox);
  }

  // Add scroll listener to detect when user manually scrolls
  logBox.addEventListener("scroll", function () {
    // Only mark as user scrolled if auto-scroll is on and they scroll up
    if (autoScroll && !isScrolledToBottom(logBox)) {
      userScrolled = true;
    }

    // If they scroll to bottom, reset userScrolled
    if (isScrolledToBottom(logBox)) {
      userScrolled = false;
    }
  });
});
