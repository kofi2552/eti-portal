// static/js/transition_admin.js
function showTab(tab) {
  document.getElementById("tab-content-lock").classList.add("hidden");
  document.getElementById("tab-content-transition").classList.add("hidden");
  document
    .getElementById("tab-lock")
    .classList.remove("border-blue-600", "text-blue-600");
  document
    .getElementById("tab-transition")
    .classList.remove("border-blue-600", "text-blue-600");

  if (tab === "lock") {
    document.getElementById("tab-content-lock").classList.remove("hidden");
    document
      .getElementById("tab-lock")
      .classList.add("text-blue-600", "border-blue-600");
  } else {
    document
      .getElementById("tab-content-transition")
      .classList.remove("hidden");
    document
      .getElementById("tab-transition")
      .classList.add("text-blue-600", "border-blue-600");
  }
}

function openConfirm() {
  const programId = document.getElementById("program-select").value;
  if (!programId) {
    alert("Please select a program first.");
    return;
  }
  document.getElementById("confirm-modal").classList.remove("hidden");
}
function closeConfirm() {
  document.getElementById("confirm-modal").classList.add("hidden");
}

function openProgress() {
  document.getElementById("progress-log").innerText = "";
  document.getElementById("progress-modal").classList.remove("hidden");
  document.getElementById("progress-close").classList.add("hidden");
}

function closeProgress() {
  document.getElementById("progress-modal").classList.add("hidden");
}

async function startTransition() {
  closeConfirm();
  const programId = document.getElementById("program-select").value;
  if (!programId) return alert("Select program.");

  openProgress();

  const logNode = document.getElementById("progress-log");
  logNode.innerText = "Starting transition...\\n";

  // Prepare POST
  const csrfToken = document.querySelector("[name=csrfmiddlewaretoken]").value;
  const data = new FormData();
  data.append("program_id", programId);

  try {
    // POST to server
    const resp = await fetch("{% url 'academics:start_program_transition' %}", {
      method: "POST",
      headers: { "X-CSRFToken": csrfToken },
      body: data,
    });

    const json = await resp.json();

    if (!json.success) {
      logNode.innerText += "\\nERROR: " + (json.error || "Unknown error");
      document.getElementById("progress-close").classList.remove("hidden");
      return;
    }

    // Print logs returned from server
    if (json.logs && Array.isArray(json.logs)) {
      for (const line of json.logs) {
        logNode.innerText += line + "\\n";
      }
    }

    logNode.innerText += "\\n--- SUMMARY ---\\n";
    logNode.innerText += "Created: " + (json.created_count || 0) + "\\n";
    logNode.innerText +=
      "Deactivated: " + (json.deactivated_count || 0) + "\\n";
    logNode.innerText +=
      "Promoted: " +
      (json.promoted_count || json.promoted_count === 0
        ? json.promoted_count
        : json.promoted_count || 0) +
      "\\n";

    document.getElementById("progress-close").classList.remove("hidden");
  } catch (err) {
    logNode.innerText += "\\nCRITICAL ERROR: " + err.message;
    document.getElementById("progress-close").classList.remove("hidden");
  }
}
