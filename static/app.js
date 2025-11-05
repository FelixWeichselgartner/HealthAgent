// Drag & Drop mit SortableJS
document.querySelectorAll(".dropzone").forEach(zone => {
  new Sortable(zone, {
    group: "days",
    animation: 120,
    ghostClass: "drag-ghost",
    onEnd: function (evt) {
      const day = parseInt(evt.to.dataset.day);
      const ids = [...evt.to.querySelectorAll(".card")].map(c => c.dataset.id);
      fetch("/api/reorder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ day, order: ids })
      });
    }
  });
});

// Modal
const modal = document.getElementById("workout-modal");
const form = document.getElementById("workout-form");
const wId = document.getElementById("w-id");
const wDay = document.getElementById("w-day");
const wType = document.getElementById("w-type");
const wTitle = document.getElementById("w-title");
const wDuration = document.getElementById("w-duration");
const wIntensity = document.getElementById("w-intensity");
const wNotes = document.getElementById("w-notes");
const strengthRow = document.getElementById("strength-row");
const cardioRow = document.getElementById("cardio-row");
const exList = document.getElementById("strength-list");
const exTpl = document.getElementById("ex-item-tpl");
const btnAddEx = document.getElementById("btn-add-ex");

function openModal(data){
  wId.value = data?.id || "";
  wDay.value = data?.day ?? 0;
  wType.value = data?.wtype || "cardio";
  wTitle.value = data?.title || "";
  wDuration.value = data?.duration_min ?? "";
  wIntensity.value = data?.intensity || "";
  wNotes.value = data?.notes || "";

  toggleTypeRows();

  // Strength exercises render
  exList.innerHTML = "";
  if (data?.exercises?.length){
    data.exercises.forEach(e => addExRow(e.exercise_id, e.sets, e.reps));
  }
  modal.showModal();
}

function toggleTypeRows(){
  if (wType.value === "strength") {
    strengthRow.style.display = "block";
    cardioRow.style.display = "none";
  } else if (wType.value === "cardio") {
    strengthRow.style.display = "none";
    cardioRow.style.display = "grid";
  } else {
    strengthRow.style.display = "none";
    cardioRow.style.display = "none";
  }
}
wType.addEventListener("change", toggleTypeRows);

function addExRow(selectedId=null, sets=3, reps=12){
  const node = exTpl.content.cloneNode(true);
  const sel = node.querySelector(".ex-select");
  EXERCISES.forEach(e => {
    const opt = document.createElement("option");
    opt.value = e.id; opt.textContent = e.name;
    if (selectedId && parseInt(selectedId) === e.id) opt.selected = true;
    sel.appendChild(opt);
  });
  node.querySelector(".ex-sets").value = sets;
  node.querySelector(".ex-reps").value = reps;
  node.querySelector(".ex-del").addEventListener("click", (ev)=>{
    ev.currentTarget.closest(".ex-item").remove();
  });
  exList.appendChild(node);
}

btnAddEx.addEventListener("click", ()=> addExRow());

// Add new workout
document.getElementById("btn-add-workout").addEventListener("click", ()=>{
  openModal({ day: 0, wtype:"cardio", title:"Neues Training" });
});

// Edit / Delete buttons
document.querySelectorAll(".card .edit").forEach(btn=>{
  btn.addEventListener("click", async (e)=>{
    const id = e.currentTarget.dataset.id;
    const res = await fetch("/api/workouts");
    const all = await res.json();
    const data = all.find(x=> x.id == id);
    openModal(data);
  });
});
document.querySelectorAll(".card .del").forEach(btn=>{
  btn.addEventListener("click", async (e)=>{
    const id = e.currentTarget.dataset.id;
    if (!confirm("Training wirklich löschen?")) return;
    await fetch(`/api/workout/${id}`, { method: "DELETE" });
    location.reload();
  });
});

// Save
form.addEventListener("close", async (ev)=>{
  if (form.returnValue !== "save") return;
  const id = wId.value;
  const payload = {
    day: parseInt(wDay.value),
    wtype: wType.value,
    title: wTitle.value,
    duration_min: wDuration.value ? parseInt(wDuration.value) : null,
    intensity: wIntensity.value || null,
    notes: wNotes.value || null
  };

  if (id) {
    await fetch(`/api/workout/${id}`, { method:"PATCH", headers:{ "Content-Type":"application/json" }, body: JSON.stringify(payload) });
    if (wType.value === "strength") {
      const exPayload = { exercises: [] };
      exList.querySelectorAll(".ex-item").forEach(row=>{
        exPayload.exercises.push({
          exercise_id: parseInt(row.querySelector(".ex-select").value),
          sets: parseInt(row.querySelector(".ex-sets").value),
          reps: parseInt(row.querySelector(".ex-reps").value)
        });
      });
      await fetch(`/api/workout/${id}/exercises`, { method:"PUT", headers:{ "Content-Type":"application/json" }, body: JSON.stringify(exPayload)});
    }
  } else {
    // create, then add exercises if strength
    const res = await fetch(`/api/workouts`, { method:"POST", headers:{ "Content-Type":"application/json" }, body: JSON.stringify({ ...payload, position: 999 })});
    const created = await res.json();
    if (wType.value === "strength") {
      const exPayload = { exercises: [] };
      exList.querySelectorAll(".ex-item").forEach(row=>{
        exPayload.exercises.push({
          exercise_id: parseInt(row.querySelector(".ex-select").value),
          sets: parseInt(row.querySelector(".ex-sets").value),
          reps: parseInt(row.querySelector(".ex-reps").value)
        });
      });
      await fetch(`/api/workout/${created.id}/exercises`, { method:"PUT", headers:{ "Content-Type":"application/json" }, body: JSON.stringify(exPayload)});
    }
  }
  location.reload();
});
