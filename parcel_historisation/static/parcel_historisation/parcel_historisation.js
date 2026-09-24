
document.getElementById("nav-saisie-tab").onclick = () => {
  if (ph.activecadastre !== null) {
    document.getElementById("step1").style.display = "block";
    document.getElementById("step2").style.display = "none";
  } else {
    document.getElementById("cadastre_selector").style.display = "block";
    document.getElementById("nav-listing-tab").classList.add("disabled");
    document.getElementById("nav-control-tab").classList.add("disabled");
  }
}

document.getElementById("plan_list").onchange = () => {
  const val = document.getElementById("plan_list").value;
  document.getElementById("desgn_list").value = val;
}

document.getElementById("desgn_list").onchange = () => {
  const val = document.getElementById("desgn_list").value;
  document.getElementById("plan_list").value = val;
}

document.getElementById("close-saisie").onclick = () => {
  ph.initialize_form();
}

document.getElementById("close-saisie-2").onclick = () => {
  ph.initialize_form();
}

document.getElementById("run-control").onclick = () => {
  ph.run_control();
}

document.getElementById("load-desgn").onclick = () => {
  const id = document.getElementById("desgn_list").value;
  ph.get_download_path(id, 'designation');
}


document.getElementById("load-plan").onclick = () => {
  const id = document.getElementById("plan_list").value;
  ph.get_download_path(id, 'plan');
}

document.getElementById("nav-listing-tab").onclick = () => {
  document.getElementById("step1").style.display = "none";
  document.getElementById("step2").style.display = "none";
  ph.load_table();
};

document.getElementById("nav-control-tab").onclick = () => {
  document.getElementById("step1").style.display = "none";
  document.getElementById("step2").style.display = "none";
};
/*
document.getElementById("saisie-tab").onclick = () => {
  document.getElementById("saisie-tab").classList.add("active");
  document.getElementById("control_section").classList.remove("active");
  document.getElementById("saisie-tab-pane").style.display = "block";
};
*/

document.getElementById("load-infolica").onclick = () => {
  const no_infolica = document.getElementById("no_infolica").value;
  ph.getBalance(no_infolica);
  ph.setCadastreListeBalance();
};

document.getElementById("balance-add-old-bf").onclick = () => {
  let balance_old_bf = document.getElementById("balance-old-bf").value;
  const balance_old_bf_serie = Number(document.getElementById("balance-old-bf-serie").value);
  const selected_cadastre = document.getElementById("cadastre-list-balance").value;

  if (!balance_old_bf && typeof balance_old_bf !== 'number') {
    return;
  }
  balance_old_bf = Number(balance_old_bf);

  if (document.getElementById('tableau-balance').firstChild === null) {
    document.getElementById('tableau-balance').innerHTML = `<table id="balance" style="border: solid 1pt black"><tr><td /></tr></table>`;
  }

  const tableau_balance = document.getElementById('tableau-balance').firstChild;
  const nb_rows = tableau_balance.rows.length;
  const nb_cols = tableau_balance.rows[0].cells.length;

  // check if old bf already is in balance
  let old_bf_user_tmp;
  let old_bf_table_tmp;
  for (let j = 0; j < balance_old_bf_serie; j++) {
    old_bf_user_tmp = selected_cadastre + "_" + (balance_old_bf + j);
    for (let i = 1; i < nb_rows; i++) {
      old_bf_table_tmp = tableau_balance.rows[i].cells[0].innerHTML.split(' ')[0];

      if (old_bf_user_tmp === old_bf_table_tmp) {
        alert(`Le bien-fonds ${old_bf_user_tmp} existe déjà dans la balance (ligne ${i + 1}).\n\nLa balance n'est pas mise à jour.`);
        return;
      }
    }
  }

  // Add old parcels
  let relation;
  for (let j = 0; j < balance_old_bf_serie; j++) {
    let row = tableau_balance.insertRow(-1);
    let cell = row.insertCell(0);

    cell.outerHTML = '<td style="text-align: right; padding: 5pt; border: solid 1pt black">' + selected_cadastre + '_' + balance_old_bf + ` <a href="javascript:balance_removeBF('${selected_cadastre}_${balance_old_bf}', 'old')" title="supprimer le bien-fonds">[-]</a></td>`;

    for (let i = 1; i < nb_cols; i++) {
      cell = row.insertCell(i);
      relation = selected_cadastre + '_' + balance_old_bf + '-' + tableau_balance.rows[0].cells[i].innerText.split(' ')[0];
      cell.outerHTML = `<td style="text-align: center; padding: 5pt; border: solid 1pt black"><input type="checkbox" id="${relation}" title="${relation}"></input></td>`;
    }

    balance_old_bf += 1;
  }

  document.getElementById("balance-old-bf").value = '';
  document.getElementById("balance-old-bf-serie").value = 1;
};

// add old dp
document.getElementById("balance-add-old-dp").onclick = () => {
  if (document.getElementById('tableau-balance').firstChild === null) {
    document.getElementById('tableau-balance').innerHTML = `<table id="balance" style="border: solid 1pt black"><tr><td style="text-align: center; padding: 5pt; border: solid 1pt black"></tr></table>`;
  }

  const tableau_balance = document.getElementById('tableau-balance').firstChild;
  const nb_rows = tableau_balance.rows.length;
  const nb_cols = tableau_balance.rows[0].cells.length;

  // check if new bf already is in balance
  let new_bf_user_tmp = "dp";
  let new_bf_table_tmp;
  for (let i = 1; i < nb_rows; i++) {
    new_bf_table_tmp = tableau_balance.rows[i].cells[0].innerText.split(' ')[0];

    if (new_bf_user_tmp === new_bf_table_tmp) {
      alert(`Un DP existe déjà dans la balance (ligne ${i + 1}).\n\nLa balance n'est pas mise à jour.`);
      return;
    }
  }

  // Add old parcels
  let row = tableau_balance.insertRow(-1)
  let cell = row.insertCell(0)

  cell.outerHTML = `<td style="text-align: right; padding: 5pt; border: solid 1pt black">dp <a href="javascript:balance_removeBF('dp', 'old')" title="supprimer le bien-fonds">[-]</a></td>`;

  let relation;
  for (let i = 1; i < nb_cols; i++) {
    cell = row.insertCell(i);
    relation = 'dp-' + tableau_balance.rows[0].cells[i].innerText.split(' ')[0];
    cell.outerHTML = `<td style="text-align: center; padding: 5pt; border: solid 1pt black"><input type="checkbox" id="${relation}" title="${relation}"></input></td>`;
  }
};

document.getElementById("balance-add-new-bf").onclick = () => {
  let balance_new_bf = document.getElementById("balance-new-bf").value;
  const balance_new_bf_serie = Number(document.getElementById("balance-new-bf-serie").value);
  const selected_cadastre = document.getElementById("cadastre-list-balance").value;

  if (!balance_new_bf && typeof balance_new_bf !== 'number') {
    return;
  }

  balance_new_bf = Number(balance_new_bf);

  if (document.getElementById('tableau-balance').firstChild === null) {
    document.getElementById('tableau-balance').innerHTML = `<table id="balance" style="border: solid 1pt black"><tr><td /></tr></table>`;
  }

  const tableau_balance = document.getElementById('tableau-balance').firstChild;
  const nb_rows = tableau_balance.rows.length;
  const nb_cols = tableau_balance.rows[0].cells.length;

  // check if new bf already is in balance
  let new_bf_user_tmp;
  let new_bf_table_tmp;
  for (let j = 0; j < balance_new_bf_serie; j++) {
    new_bf_user_tmp = selected_cadastre + "_" + (balance_new_bf + j);
    for (let i = 1; i < nb_cols; i++) {
      new_bf_table_tmp = tableau_balance.rows[0].cells[i].innerHTML.split(' ')[0];

      if (new_bf_user_tmp === new_bf_table_tmp) {
        alert(`Le bien-fonds ${new_bf_user_tmp} existe déjà dans la balance (colonne ${i + 1}).\n\nLa balance n'est pas mise à jour.`);
        return;
      }
    }
  }

  // Add new parcels
  let relation;
  for (let j = 0; j < balance_new_bf_serie; j++) {
    let cell = tableau_balance.rows[0].insertCell(-1);

    cell.outerHTML = '<td style="text-align: center; padding: 5pt; border: solid 1pt black; vertical-align: bottom;"><span style="writing-mode: tb-rl; transform: rotate(-180deg);" title="' + selected_cadastre + '_' + balance_new_bf + '">' + selected_cadastre + '_' + balance_new_bf + '</span>' + ` <a href="javascript:balance_removeBF('${selected_cadastre}_${balance_new_bf}', 'new')" title="supprimer le bien-fonds">[-]</a></td>`;

    for (let i = 1; i < nb_rows; i++) {
      cell = tableau_balance.rows[i].insertCell(-1);
      relation = tableau_balance.rows[i].cells[0].innerText.split(' ')[0] + '-' + selected_cadastre + '_' + balance_new_bf;
      cell.outerHTML = `<td style="text-align: center; padding: 5pt; border: solid 1pt black"><input type="checkbox" id="${relation}" title="${relation}"></input></td>`;
    }

    balance_new_bf += 1;
  }

  document.getElementById("balance-new-bf").value = '';
  document.getElementById("balance-new-bf-serie").value = 1;
};

// add new dp
document.getElementById("balance-add-new-dp").onclick = () => {
  if (document.getElementById('tableau-balance').firstChild === null) {
    document.getElementById('tableau-balance').innerHTML = `<table id="balance" style="border: solid 1pt black"><tr><td style="text-align: center; padding: 5pt; border: solid 1pt black"></tr></table>`;
  }

  const tableau_balance = document.getElementById('tableau-balance').firstChild;
  const nb_rows = tableau_balance.rows.length;
  const nb_cols = tableau_balance.rows[0].cells.length;

  // check if new bf already is in balance
  let new_bf_user_tmp = "dp";
  let new_bf_table_tmp;
  for (let i = 1; i < nb_cols; i++) {
    new_bf_table_tmp = tableau_balance.rows[0].cells[i].innerText.split(' ')[0];

    if (new_bf_user_tmp === new_bf_table_tmp) {
      alert(`Un DP existe déjà dans la balance (colonne ${i + 1}).\n\nLa balance n'est pas mise à jour.`);
      return;
    }
  }

  // Add new parcels
  let cell = tableau_balance.rows[0].insertCell(-1);
  cell.outerHTML = `<td style="text-align: center; padding: 5pt; border: solid 1pt black; vertical-align: bottom;"><span style="writing-mode: tb-rl; transform: rotate(-180deg);" title="dp">dp</span> <a href="javascript:balance_removeBF('dp', 'new')" title="supprimer le bien-fonds">[-]</a></td>`;

  let relation;
  for (let i = 1; i < nb_rows; i++) {
    cell = tableau_balance.rows[i].insertCell(-1);
    relation = tableau_balance.rows[i].cells[0].innerText.split(' ')[0] + '-dp';
    cell.outerHTML = `<td style="text-align: center; padding: 5pt; border: solid 1pt black"><input type="checkbox" id="${relation}" title="${relation}"></input></td>`;
  }
};

// submit-relations
document.getElementById("submit-relations").onclick = async () => {
  const relations = getBalanceRelations();
  const ddp = getDDPRelations();

  const check = ph.check_relations();
  if (check === true) {
    // post relations
    await postBalanceRelations(relations, ddp);
  }
}


document.getElementById("submit-balance-file").onclick = () => {
  ph.postBalanceFile();
}


document.getElementById("create-ddp").onclick = () => {
  const ddp_number = Number(document.getElementById("ddp-number").value);
  const ddp_base_number = Number(document.getElementById("ddp-base-number").value);

  // check for no-empty fields
  if (!(ddp_number && ddp_base_number)) {
    alert("Veuillez compléter les champs 'DDP' et 'Bf de base'");
    return;
  }

  // check that ddp_number > ddp_base_number
  if (ddp_number < ddp_base_number) {
    if (!confirm(`Le DDP est-il défini sur un bien-fonds avec un numéro plus élevé ?\n\nDDP: ${ddp_number}\nBien-fonds de base: ${ddp_base_number}`)) {
      return;
    };
  }
  if (ddp_number === ddp_base_number) {
    alert(`Le numéro de DDP et le numéro du bien-fonds de base sont identiques. La saisie n'est pas ajoutée à la liste.`);
    return;
  }

  const ddp = [ph.activecadastre, ddp_number].join("_");
  const base = [ph.activecadastre, ddp_base_number].join("_");
  ph.createNewHTMLddp(ddp, base);
}

document.getElementById("load-operation").onclick = () => {
  const plan_link = document.getElementById("plan-link-continue").value;
  if (!plan_link) {
    alert("Veuillez entrer le numéro de fichier afin de poursuivre le processus.");
    return;
  }

  ph.loadOperation(plan_link);
}


document.getElementById("plan-link-continue").addEventListener("keypress", e => {
  if (e.key === 'Enter') {
    document.getElementById("load-operation").click();
    document.getElementById("plan-link-continue-results").innerHTML = "";
  }
});

document.getElementById("plan-link-continue").addEventListener("change", e => {
  document.getElementById("load-operation").click();
  document.getElementById("plan-link-continue-results").innerHTML = "";
});


document.getElementById("plan-link-continue").addEventListener("keyup", e => {
  if (e.key) {

    let params = {
      searchterm: document.getElementById("plan-link-continue").value,
      numcad: ph.activecadastre,
    }

    return fetch('search_plans_by_term', {
      method: 'POST',
      headers: {
        'X-CSRFToken': ph.csrftoken
      },
      body: JSON.stringify(params)
    }).then((response) => response.json())
      .then((data) => {

        options_html = "";
        data.forEach(x => {options_html += `<option>${x}</option>`});
        document.getElementById("plan-link-continue-results").innerHTML = options_html;

      }).catch((err) => {
        alert('Une erreur s\'est produite. Veuillez contacter l\'administrateur\n\n \
        Détail de l\'erreur:\n' + String(err));
      });
  }
});



// Fonction pour vérifier et mettre à jour la visibilité de la div container
function updateContainerVisibility() {
  const html_id = ["ddp-section", "tableau-balance"];

  for (sct of html_id) {
    const container = document.getElementById(`${sct}-container`);
    const inner = document.getElementById(sct);

    if (inner && inner.hasChildNodes() && inner.childNodes.length > 0 && inner.innerHTML.trim() !== "") {
      container.hidden = false;
    } else {
      container.hidden = true;
    }
  }
}

// Configuration de MutationObserver pour surveiller les changements dans les div inner
const observer = new MutationObserver(updateContainerVisibility);
// Cibler les div inner et commencer à observer
const ddp_section_inner = document.getElementById('ddp-section-container');
observer.observe(ddp_section_inner, { childList: true, subtree: true });
const tableau_balance_inner = document.getElementById('tableau-balance-container');
observer.observe(tableau_balance_inner, { childList: true, subtree: true });
document.addEventListener("DOMContentLoaded", updateContainerVisibility);


function handleEnterAsClick(e, elementId) {
  if (e.keyCode === 13) {
    e.preventDefault();
    document.getElementById(elementId).click();
  }
}

function getBalanceRelations() {
  let relations = new Array();

  const tableau_balance = document.getElementById('tableau-balance').firstChild;

  if (tableau_balance === null) {
    return null;
  }

  // Go through the table and find relations
  let row_idx = 0;
  let cell_idx;
  for (const row of tableau_balance.rows) {
    cell_idx = 0
    for (const cell of row.cells) {
      if (row_idx !== 0 && cell_idx !== 0 && cell.firstChild.tagName === "INPUT" && cell.firstChild.checked) {
        relations.push(cell.firstChild.id)
      }
      cell_idx += 1;
    }
    row_idx += 1;
  }

  return relations;
}

function getDDPRelations() {
  let relations = new Array();

  const ddp_section = document.getElementById('ddp-section');

  if (ddp_section.childElementCount === 0) {
    return null;
  }

  // Go through children and find relations
  for (const ddp of ddp_section.children) {
    relations.push(ddp.id);
  }

  return relations;
}


async function postBalanceRelations(balance, ddp) {
  // let no_infolica = document.getElementById("no_infolica").value;

  let params = {
    division_id: ph.active_plan_link,
    no_infolica: no_infolica,
    cadastre_id: ph.activecadastre,
    balance: balance,
    ddp: ddp,
  }

  return fetch('submit_balance', {
    method: 'POST',
    headers: {
      'X-CSRFToken': ph.csrftoken
    },
    body: JSON.stringify(params)
  }).then((response) => response.json())
    .then((data) => {
      ph.showSuccessMessage(title="Succès !", body="✅ La balance a bien été enregistrée");
      // hide balance and DDP sections
      document.getElementById("tableau-balance").innerHTML = '';
      document.getElementById("ddp-section").innerHTML = '';

      ph.reset_step1();
      document.getElementById("choose_cadastre").click();

    }).catch((err) => {
      alert('Une erreur s\'est produite. Veuillez contacter l\'administrateur\n\n \
      Détail de l\'erreur:\n' + String(err));
    });
}


ph = {
  activecadastre: null,
  cadastres: {},
  active_plan_link: null,
  operationDetail: new bootstrap.Modal(document.getElementById('operationDetail')),

};

ph.initApplication = function () {
  // Token is needed for calling Django using POST
  ph.csrftoken = document.querySelector('[name=csrfmiddlewaretoken]').value;
  ph.load_cadastre("cadastre_list");
};

// Gets the list of cadastre (application entry point)
ph.load_cadastre = async (html_element_id) => {
  const select = document.getElementById(html_element_id);
  let i, L = select.options.length - 1;
  for (i = L; i >= 0; i--) {
    select.remove(i);
  }
  fetch("../cadastre/get")
    .then((response) => response.json())
    .then((data) => {
      for (let i = 0; i < data.length; i++) {
        let item = data[i];
        let element = document.createElement("option");
        ph.cadastres[item["numcad"]] = item["cadnom"];
        element.innerText = item["cadnom"];
        element.value = item["numcad"];
        select.append(element);
        document.getElementById("overlay").style.display = "none";
        //   document.getElementById("control_section").classList.add("disabled");
        document.getElementById("cadastre_selector").style.display = "block";
      }
    });
  return;
};

function removeOptions(selectElement) {
  var i, L = selectElement.options.length - 1;
  for (i = L; i >= 0; i--) {
    selectElement.remove(i);
  }
}

// Choosing a cadastre sends user to step 1 display
document.getElementById("choose_cadastre").onclick = () => {

  document.getElementById("overlay").style.display = "block";
  const e = document.getElementById("cadastre_list");
  const selected_value = e.options[e.selectedIndex].value;
  const url = "get_docs_list?" + new URLSearchParams({
    numcad: selected_value
  });

  fetch(url)
    .then((response) => response.json())
    .then((data) => {
      let item; let element;
      const plan_list = document.getElementById("plan_list");
      const desgn_list = document.getElementById("desgn_list");
      removeOptions(plan_list);
      removeOptions(desgn_list);
      const list = data['list'];
      for (let i = 0; i < list.length; i++) {
        item = list[i];
        element = document.createElement("option");
        element.innerText = item["link"];
        element.value = item["id"];
        plan_list.append(element);
        element = document.createElement("option");
        element.value = item["id"];
        if (item['designation_id'] !== null) {
          element.innerText = item["link"];
        } else {
          element.innerText = "-";
        }
        desgn_list.append(element);
      }
      ph.activecadastre = document.getElementById("cadastre_list").value;
      document.getElementById("cadastre_selector").style.display = "none";
      document.getElementById("step1").style.display = "block";
      const cadastre_text_tags = document.querySelectorAll(".cadastre_text");
      for (let i = 0; i < cadastre_text_tags.length; i++) {
        cadastre_text_tags[i].innerText = ph.cadastres[ph.activecadastre];
      }
      document.getElementById("overlay").style.display = "none";
      document.getElementById("nav-listing-tab").classList.remove("disabled");
      document.getElementById("nav-control-tab").classList.remove("disabled");

      const download_path = data['download'];

      // The most recent document is automatically opened, might it be a plan or a designation
      // (currently commented because of development purposes)
      /*
       ph.get_document(download_path)
      */
    });
};

// The download path is the direct access to documents (plans or designation)
// They are fetched on the fly when needed
ph.get_download_path = (id, type) => {
  const url = "get_download_path?" + new URLSearchParams({
    id: id,
    type: type
  });
  fetch(url)
    .then((response) => response.json())
    .then((data) => {
      ph.get_document(data["download_path"]);
    });
};

// Using the download path (which is fetch using the upper function),
// a document can be fetched.
ph.get_document = (download_path) => {
  const download_file = download_path.split('/').at(-1);
  fetch('download/' + download_path)
    .then(res => res.blob())
    .then(data => {
      let a = document.createElement("a");
      a.href = window.URL.createObjectURL(data);
      a.download = download_file;
      a.click();
      window.URL.revokeObjectURL('download/' + download_path);
    });
};

// Submitting data from the step 1 form.
document.getElementById("submit-form").onclick = () => {

  document.getElementById("overlay").style.display = "block";

  // check that at least one option is selected
  if ((document.getElementById("div_check").checked || document.getElementById("cad_check").checked || document.getElementById("serv_check").checked || document.getElementById("art35_check").checked || document.getElementById("other_check").checked || document.getElementById("delayed_check").checked) === false) {
    ph.showErrorMessage(title="Erreur !", body="❌ La tâche n'a été exécutée.<br>Sélectionner un type d'affaire.");
    document.getElementById("overlay").style.display = "none";
    return;
  }

  const delayed_check = document.getElementById("delayed_check").checked
  ph.setCadastreListeBalance();

  const params = {
    id: document.getElementById("plan_list").value,
    div_check: document.getElementById("div_check").checked,
    cad_check: document.getElementById("cad_check").checked,
    serv_check: document.getElementById("serv_check").checked,
    art35_check: document.getElementById("art35_check").checked,
    other_check: document.getElementById("other_check").checked,
    delayed_check: delayed_check,
    complement: document.getElementById("complement").value,
    plan_link: ph.active_plan_link,
    operation_id: ph.active_operation_id,
  };


  // A delayed plan can only be delayed, nothing else can be done
  if (delayed_check === true) {
    let text = "Une désignation ou un plan retardé ne permet pas d'enregistrer d'autres informations";
    text += "\n\nSeul le retard est enregistré. De plus, il faudra procéder via l'interface de contrôle."
    if (confirm(text) == false) {
      return;
    }
  }

  // submitting with the token because Django needs it when doing a POST request
  fetch('submit_saisie', {
    method: ph.active_operation_id? 'PUT': 'POST',
    headers: {
      'Accept': 'application/json, text/plain,  */*',
      'Content-Type': 'application/json'
    },
    headers: { 'X-CSRFToken': ph.csrftoken },
    mode: 'same-origin',
    body: JSON.stringify(params),
  })
    .then(res => res.json())
    .then(res => {
      ph.active_plan_link = res['operation_id'];
      ph.resetSubmitForm(res['has_div']);
    });
};

// Data submission was sucessfull: resetting form and opening balance interface (if it is a division)
ph.resetSubmitForm = async (div) => {
  // Open div panel (if div)
  document.getElementById("step1").style.display = "none";
  if (div === true) {
    document.getElementById("step2").style.display = "block";
    document.getElementById("overlay").style.display = "none";
    document.getElementById("operation_id_title").innerText = ph.active_plan_link;
    document.getElementById("operation_id_title_section").hidden = false;

    if (ph.active_operation_id) {
      ph.loadBalance();
    }
  } else {
    document.getElementById("operation_id_title_section").hidden = true;
    document.getElementById("choose_cadastre").click();
    ph.reset_step1();
  }
};

// Global table showing all records for a given cadastre
// Two action buttons enable to show details or to change the
// plan/designation status.
ph.load_table = () => {
  document.getElementById("overlay").style.display = "block";

  const url = "api/plans?" + new URLSearchParams({
    numcad: ph.activecadastre,
    format: 'json'
  });

  ph.list_grid = new gridjs.Grid({
    columns: [
      'N° plan',
      {
        name: 'Designation',
        formatter: (cell) => cell ? cell.replace('.pdf', '') : null
      },
      'État',
      'Date plan',
      {
        name: 'Actions',
        sort: false,
        formatter: (cell, row) => {
          if (row.cells[2].data !== 'A faire') {
            return new gridjs.h('button', {
              className: 'btn btn-secondary',
              onClick: () => ph.changeStatus(row.cells[4].data, 'free')
            }, 'Libérer');
          }
        },
      },
      {
        name: 'Détails',
        sort: false,
        formatter: (cell, row) => {
          if (row.cells[2].data !== 'A faire') {
            return new gridjs.h('button', {
              className: 'btn btn-secondary',
              onClick: () => ph.showDetail(row.cells[5].data)
            }, 'Détails');
          }
        },
      },
    ],
    server: {
      url: url,
      then: (data) => data.results.map(plan =>
        [
          plan.plan_number,
          plan.designation,
          plan.state,
          plan.date_plan,
          plan.id,
          plan.operation_id
        ]
      ),
      total: data => data.count,
    },
    pagination: {
      limit: 20,
      server: {
        url: (prev, page) => {
          page += 1;
          return `${prev}&page=${page}`;
        }
      }
    },
    sort: {
      multiColumn: false,
      server: {
        url: (prev, columns) => {
          if (!columns.length) return prev;
          const column_names = [
            'plan',
            'designation',
            'state',
            'date_plan',
          ];
          const col = columns[0];
          const dir = col.direction === 1 ? '' : '-';
          let colName = column_names[col.index];
          return `${prev}&ordering=${dir}${colName}`;
        }
      }
    },
    search: {
      server: {
        url: (prev, keyword) => `${prev}?search=${keyword}`
      }
    },
    language: {
      'search': {
        'placeholder': 'Rechercher...'
      },
      'pagination': {
        'previous': 'Précédent',
        'next': 'Suivant',
        'showing': 'Affichage de l\'élément',
        'to': 'à',
        'of': 'sur',
        'results': 'éléments'
      }
    }
  });

  ph.list_grid.render(document.getElementById("plan-list-table"));

  document.getElementById("overlay").style.display = "none";
};

// Build HMTL for balance
ph.buildHTMLTable = (balance) => {
  let relation;
  let tb_html = '<table id="balance" style="border: solid 1pt black">'
  for (let i = 0; i < balance.length; i++) {
    tb_html += '<tr>';
    for (let j = 0; j < balance[0].length; j++) {
      if (i === 0 && j === 0) {
        tb_html += '<td />';
      } else if (i > 0 && j > 0) {
        relation = `${balance[i][0]}-${balance[0][j]}`;
        tb_html += `<td style="text-align: center; padding: 5pt; border: solid 1pt black"><input type="checkbox" id="${relation}" title="${relation}" ${(balance[i][j].toLowerCase() === 'x' ? 'checked' : '')}></input></td>`;
      } else if (i === 0) {
        tb_html += `<td style="text-align: center; padding: 5pt; border: solid 1pt black; vertical-align: bottom;"><span style="writing-mode: tb-rl; transform: rotate(-180deg);" title="${balance[i][j]}">${(balance[i][j] ? balance[i][j] : '')}</span>${((i !== 0 ^ j !== 0) ? ` <a href="javascript:balance_removeBF('${balance[i][j]}', 'new')" title="supprimer le bien-fonds">[-]</a>` : '')}</td>`;
      } else {
        tb_html += `<td style="text-align: right; padding: 5pt; border: solid 1pt black;">${(balance[i][j] ? balance[i][j] + ((i !== 0 ^ j !== 0) ? ` <a href="javascript:balance_removeBF('${balance[i][j]}', 'old')" title="supprimer le bien-fonds">[-]</a>` : '') : '')}</td>`;
      }
    }
    tb_html += '</tr>';
  }
  tb_html += '</table>';
  return tb_html;
}

ph.createNewHTMLddp = (ddp, base) => {
  const ddp_span_id = `${ddp}-${base}`;
  let ddp_section = document.getElementById("ddp-section");

  for (const elem of ddp_section.children) {
    if (ddp_span_id === elem.id) {
      alert(`Le DDP a déjà été saisi dans la liste.\n\n${[ph.activecadastre, ddp_number].join("_")}/${[ph.activecadastre, ddp_base_number].join("_")}`)
      return;
    }
  }

  ddp_section.innerHTML += `<span id="${ddp_span_id}" class="badge rounded-pill bg-primary m-1"><span style="font-size: 1.5em">
                              ${ddp}</span>/${base}
                              <button id="close" onclick="this.parentElement.remove()" class="rounded-circle" style="border: 0px; margin-left: 5px;">X</button>
                            </span>`
}

// Get balance from infolica
ph.getBalance = (id) => {
  document.getElementById("load-infolica-status").innerHTML = "";

  fetch(ph.infolica_api_url + 'balance_from_affaire_id?' + new URLSearchParams({
    division_id: id,
    cadastre_id: ph.activecadastre
  })
  )
    .then((response) => response.json())
    .then((data) => {
      if (!Object.keys(data).includes('balance')) {
        document.getElementById("load-infolica-status").innerHTML = '<p><em>(' + data.error.detail + ')</em></p>';
        document.getElementById("tableau-balance").innerHTML = "";
        return;
      }

      let balance = data.balance;

      if (balance === null) {
        document.getElementById("tableau-balance").innerHTML = '<p>Aucune balance</p>';
        return;
      }

      let tb_html = ph.buildHTMLTable(balance);

      document.getElementById("tableau-balance").innerHTML = tb_html;

    }).catch((err) => {
      alert('Une erreur s\'est produite. Veuillez contacter l\'administrateur\n\n \
      Détail de l\'erreur:\n' + String(err));
    });

  return;
};

balance_removeBF = (bf, bf_status) => {

  let table = document.getElementById("tableau-balance").children[0];
  let row_idx = 0;
  let col_idx = 0;

  for (let row of table.rows) {
    if (row_idx === 0 && bf_status === "new") {
      for (let col of row.cells) {
        if (col.innerText.split(' ')[0] === (bf)) {

          // remove column
          for (let j = 0; j < table.rows.length; j++) {
            table.rows[j].deleteCell(col_idx);
          }

          return;
        }
        col_idx += 1;
      }
    } else if (bf_status === "old") {
      if (row.cells[0].innerText.split(' ')[0] === (bf)) {

        // remove row
        document.getElementById("tableau-balance").children[0].deleteRow(row_idx);

        return;
      }
    }
    row_idx += 1;
  }
}

ph.showBalance = async (id) => {
  // close modal
  ph.operationDetail.hide();
  // change panel
  const triggerEl = document.querySelector('#nav-saisie-tab');
  bootstrap.Tab.getInstance(triggerEl).show();
  // load operation
  await ph.loadOperation(id);
  ph.active_plan_link = id;
  // simulate click on OK button to open balance
  document.getElementById("submit-form").click();
  ph.loadBalance();
}

ph.showDetail = (id) => {

  fetch(`api/operations/${id}`)
    .then(res => res.json())
    .then((data) => {

      const operations = data.operation_types;
      const div = (operations.div_check === true) ? "icon-check" : "icon-cross";
      const cad = (operations.cad_check === true) ? "icon-check" : "icon-cross";
      const serv = (operations.serv_check === true) ? "icon-check" : "icon-cross";
      const art = (operations.art35_check === true) ? "icon-check" : "icon-cross";
      const autre = (operations.other_check === true) ? "icon-check" : "icon-cross";
      const ret = (data.plan_retarde === true) ? "icon-check" : "icon-cross";
      const compl = (data.complement === null) ? "-" : data.complement;
      let compl_div = "";
      if (operations.div_check === true) {
        compl_div = `<button class="btn btn-secondary" onClick="ph.showBalance(${data.id});">Lien vers la balance</button>`;
      }
      // create details
      const tmpl = `
      <table class="op_detail_table">
        <tr><td>Fichier plan</td><td>${data.plan_name}</td></tr>
        <tr><td>Fichier désignation</td><td>${data.designation_name}</td></tr>
        <tr><td>Division / réunion</td><td><svg><use href="#${div}"/></svg><span style="float:right;">${compl_div}</span></td></tr>
        <tr><td>Cadastration, nature, etc.</td><td><svg><use href="#${cad}"/></svg></td></tr>
        <tr><td>Servitude</td><td><svg><use href="#${serv}"/></svg></td></tr>
        <tr><td>art. 35</td><td><svg><use href="#${art}"/></svg></td></tr>
        <tr><td>Autre</td><td><svg><use href="#${autre}"/></svg></td></tr>
        <tr><td>Retardé</td><td><svg><use href="#${ret}"/></svg></td></tr>
        <tr><td>Complément</td><td>${compl}</td></tr>
      </table>
    `;

      document.getElementById("operationDetailTitle").innerHTML = `Fichier ${data.id}`;
      document.getElementById("operationDetailBody").innerHTML = tmpl;
      // open modal
      ph.operationDetail.show();
    })
    .catch(err => alert("ERREUR !\nLa récupération de l'opération a échoué.\n\n", err));
};

ph.changeStatus = (id, type) => {
  fetch('liberate?' + new URLSearchParams({
    id: id,
    type: type
  }))
    .then(res => res.json())
    .then((data) => {
      ph.list_grid.forceRender();
    })
    .catch(err => alert("ERREUR !\nLe fichier n'a pas été enregistré.\n\n", err));
};

ph.postBalanceFile = () => {
  let formData = new FormData();
  formData.append('file', document.getElementById("input-balance-from-file").files[0]);
  formData.append('cadnum', document.getElementById("cadastre-list-balance").value);

  // submitting balance file to backend
  fetch('balance_file_upload', {
    method: 'POST',
    headers: {
      'Accept': 'application/json, text/plain,  */*',
      'Content-Type': 'application/json'
    },
    headers: {
      'X-CSRFToken': ph.csrftoken
    },
    mode: 'same-origin',
    body: formData,
  })
    .then(res => res.json())
    .then(res => {
      // empty file input
      document.getElementById("input-balance-from-file").value = null;
      document.getElementById("cadastre-list-balance").value = ph.activecadastre;

      let tb_html = ph.buildHTMLTable(res.balance);

      document.getElementById("tableau-balance").innerHTML = tb_html;

    })
    .catch(err => alert("ERREUR !\nLe fichier n'a pas été enregistré.\n\n", err));
}

ph.setCadastreListeBalance = () => {
  let select = document.getElementById("cadastre-list-balance");
  for (const [key, value] of Object.entries(ph.cadastres)) {
    let element = document.createElement("option");
    element.innerText = value;
    element.value = key;
    select.append(element);
  }

  document.getElementById("cadastre-list-balance").value = ph.activecadastre;
};

ph.initialize_form = () => {
  const text = "Êtes-vous sûr de vouloir quitter la saisie?\nTous les éléments saisis dans ce formulaire seront perdus.";
  if (confirm(text) == true) {
    document.getElementById("step1").style.display = "none";
    document.getElementById("cadastre_selector").style.display = "block";
    ph.activecadastre = null;
    ph.active_plan_link = null;
    ph.active_operation_id = null;
    document.getElementById("nav-listing-tab").classList.add("disabled");
    document.getElementById("nav-control-tab").classList.add("disabled");
    // Reset form
    document.getElementById("delayed_check").checked = false;
    document.getElementById("div_check").checked = false;
    document.getElementById("cad_check").checked = false;
    document.getElementById("serv_check").checked = false;
    document.getElementById("art35_check").checked = false;
    document.getElementById("other_check").checked = false;
    document.getElementById("complement").value = "";
    // Reset form div
    document.getElementById("operation_id_title_section").hidden = true;
    document.getElementById("operation_id_title").innerText = "";
    document.getElementById("step2").style.display = "none";
    document.getElementById("input-continuation-checkbox").checked = false;
    document.getElementById("operation-continue-section").hidden = true;
    document.getElementById("plan-link-continue").value = "";
    document.getElementById("no_infolica").value = "";
    // Reset cadastre text fields
    const cadastre_text_tags = document.querySelectorAll(".cadastre_text");
    for (let i = 0; i < cadastre_text_tags.length; i++) {
      cadastre_text_tags[i].innerText = ph.cadastres[ph.activecadastre];
    }
    // get rid of gridjs
    if (ph.list_grid !== undefined) {
      ph.list_grid.destroy();
    }
    document.getElementById("plan-list-table").innerHTML = "";

    // Empty control tables
    document.getElementById("run-control").style.display = "block";
    document.getElementById("source-div").classList.add("d-none");
  }
}


ph.reset_step1 = () => {
  document.getElementById("step1").style.display = "block";
  ph.active_plan_link = null;
  ph.active_operation_id = null;
  // Reset form
  document.getElementById("delayed_check").checked = false;
  document.getElementById("div_check").checked = false;
  document.getElementById("cad_check").checked = false;
  document.getElementById("serv_check").checked = false;
  document.getElementById("art35_check").checked = false;
  document.getElementById("other_check").checked = false;
  document.getElementById("complement").value = "";
  // Reset form div
  document.getElementById("operation_id_title_section").hidden = true;
  document.getElementById("operation_id_title").innerText = "";
  document.getElementById("step2").style.display = "none";
  document.getElementById("input-continuation-checkbox").checked = false;
  document.getElementById("operation-continue-section").hidden = true;
  document.getElementById("plan-link-continue").value = "";
  document.getElementById("input-continuation-checkbox").checked = false;
  document.getElementById("no_infolica").value = "";
  document.getElementById("tableau-balance").innerHTML = "";
  return;
}


ph.loadBalance = () => {
  fetch(`api/balance/${ph.active_operation_id}`)
    .then((response) => response.json())
    .then((data) => {
      if (data.balance) {
        let tb_html = ph.buildHTMLTable(data.balance);
        document.getElementById("tableau-balance").innerHTML = tb_html;
      }

      let bf;
      for (const elem of data.ddp) {
        bf = elem.split("-");
        ph.createNewHTMLddp(bf[1], bf[0]);
      }
    })
    .catch((err) => {
      alert("Une erreur est survenue dans le chargement de la balance.\nVeuillez contacter l'administrateur.\n\n" + String(err))

    })
}

ph.check_relations = () => {
  const balance = document.getElementById("balance").firstChild;

  let error;
  let errors = [];
  let sum_row;
  let sum_col;
  for (let row_id = 1; row_id < balance.rows.length; row_id++) {
    for (let col_id = 1; col_id < balance.rows[row_id].cells.length; col_id++) {
      sum_row = 0
      sum_col = 0
      // commencer les choses sérieuses: compter le nombre de "true" par ligne et par colonne
      for (let tmp_row_id = 1; tmp_row_id < balance.rows.length; tmp_row_id++) {
        // figer la colonne et parcourir les lignes
        if (balance.rows[tmp_row_id].cells[col_id].firstChild.checked === true) {
          sum_row++;
        }
      }
      for (let tmp_col_id = 1; tmp_col_id < balance.rows[row_id].cells.length; tmp_col_id++) {
        // figer la ligne et parcourir les colonnes
        if (balance.rows[row_id].cells[tmp_col_id].firstChild.checked === true) {
          sum_col++;
        }
      }
      // errors
      if (sum_row === 0) {
        // Un nouveau bien-fonds n'a pas de relation
        error = `Le bien-fonds ${balance.rows[0].cells[col_id].innerText.split(' ')[0]} n'a aucune relation.`;
        if (!errors.includes(error)) {
          errors.push(error)
        }
      }
      if (sum_col === 0) {
        // Un ancien bien-fonds n'a pas de relation
        error = `Le bien-fonds ${balance.rows[row_id].cells[0].innerText.split(' ')[0]} n'a aucune relation.`;
        if (!errors.includes(error)) {
          errors.push(error)
        }
      }
      if (sum_row === 1 && sum_col === 1 && balance.rows[row_id].cells[col_id].firstChild.checked === true) {
        // Un ancien bien-fonds est uniquement balancé dans un nouveau bien-fonds (pas divisé, pas réuni)
        error = `Le bien-fonds ${balance.rows[row_id].cells[0].innerText.split(' ')[0]} n'est pas divisé/réuni.`;
        if (!errors.includes(error)) {
          errors.push(error)
        }
      }
    }
  }

  if (errors.length>0) {
    result = confirm(`Erreurs dans la balance:\n\n${errors.join('\n')}\n\nContinuer l'enregistrement de la balance ?`);
    return result;
  } else  {
    result = confirm(`La balance a été vérifiée.\n\nPoursuivre l'enregistrement [OK] ou faut-il saisir d'autres balances [ANNULER] ?`)
  }

  return result;

}

ph.run_control = () => {
  document.getElementById("run-control").style.display = "none";
  document.getElementById("overlay").style.display = "block";

  fetch(`run_control/${ph.activecadastre}`)
    .then((response) => response.json())
    .then((data) => {
      ph.create_control_tables(data);
    })
    .catch((err) => {
      alert("Une erreur est survenue dans le chargement de la balance.\nVeuillez contacter l'administrateur.\n\n" + String(err));
    });
}

ph.create_control_tables = (data) => {
  const source = data.sources;
  const destination = data.destination;
  const source_table = document.getElementById('source_table');
  const destination_table = document.getElementById('destination_table');
  // reinitialize in case table was already populated
  const old_source_table_body = source_table.getElementsByTagName('tbody')[0];
  const source_table_body = document.createElement('tbody');
  old_source_table_body.parentNode.replaceChild(source_table_body, old_source_table_body);
  const old_destination_table_body = destination_table.getElementsByTagName('tbody')[0];
  const destination_table_body = document.createElement('tbody');
  old_destination_table_body.parentNode.replaceChild(destination_table_body, old_destination_table_body);

  let lastSourceSelectedRow = null;
  let lastDestinationSelectedRow = null;
  let new_row;
  let new_cell;
  source.forEach(element => {
    new_row = source_table_body.insertRow();
    new_cell = new_row.insertCell();
    new_cell.appendChild(document.createTextNode(element));
  });
  destination.forEach(element => {
    new_row = destination_table_body.insertRow();
    new_cell = new_row.insertCell();
    new_cell.appendChild(document.createTextNode(element));
  });
  source_table.addEventListener('click', (event) => {
    const row = event.target.closest('tr');
    if (!row || row.parentNode.tagName === 'THEAD') return; // Ignore header clicks

    if (event.ctrlKey || event.metaKey) { // Multi-selection with Ctrl
        row.classList.toggle('selected');
    } else if (event.shiftKey) { // Range selection with Shift
        if (lastSourceSelectedRow) {
            const rows = Array.from(source_table.querySelectorAll('tbody tr'));
            const start = Math.min(rows.indexOf(lastSourceSelectedRow), rows.indexOf(row));
            const end = Math.max(rows.indexOf(lastSourceSelectedRow), rows.indexOf(row));

            rows.forEach((r, index) => {
                if (index >= start && index <= end) {
                    r.classList.add('selected');
                }
            });
        }
    } else { // Single selection
        Array.from(source_table.querySelectorAll('tbody tr.selected')).forEach((r) => {
            r.classList.remove('selected');
        });
        row.classList.add('selected');
    }
    lastSourceSelectedRow = row;
  });
  destination_table.addEventListener('click', (event) => {
    const row = event.target.closest('tr');
    if (!row || row.parentNode.tagName === 'THEAD') return; // Ignore header clicks

    if (event.ctrlKey || event.metaKey) { // Multi-selection with Ctrl
        row.classList.toggle('selected');
    } else if (event.shiftKey) { // Range selection with Shift
        if (lastDestinationSelectedRow) {
            const rows = Array.from(destination_table.querySelectorAll('tbody tr'));
            const start = Math.min(rows.indexOf(lastDestinationSelectedRow), rows.indexOf(row));
            const end = Math.max(rows.indexOf(lastDestinationSelectedRow), rows.indexOf(row));

            rows.forEach((r, index) => {
                if (index >= start && index <= end) {
                    r.classList.add('selected');
                }
            });
        }
    } else { // Single selection
        Array.from(destination_table.querySelectorAll('tbody tr.selected')).forEach((r) => {
            r.classList.remove('selected');
        });
        row.classList.add('selected');
    }
    lastDestinationSelectedRow = row;
  });
  document.getElementById("source-div").classList.remove("d-none");
  document.getElementById("overlay").style.display = "none";
}

ph.loadOperation = async (plan_link) => {
  ph.reset_step1();

  await fetch(`api/operations/?plan_link=${plan_link}&cadastre_id=${ph.activecadastre}`)
    .then((response) => response.json())
    .then((data) => {

      if (data.count == 0) {
        ph.showErrorMessage();
        alert(`Aucune saisie n'a été enregistrée pour le plan ${plan_link} sur le cadastre ${ph.cadastres[ph.activecadastre]}.`);
        return;
      }
      if (data.count > 1) {
        ph.showErrorMessage();
        alert(`Il existe plusieurs saisies pour le plan ${plan_link} sur le cadastre ${ph.cadastres[ph.activecadastre]}.\nContacter l'administrateur.`);
        return;
      }

      data = data.results[0];
      ph.active_operation_id = data.id;

      // update plan list
      plan_list = document.getElementById("plan_list")
      desgn_list = document.getElementById("desgn_list")

      element = document.createElement("option");
      element.selected = true;
      element.innerText = data["plan_link"];
      element.value = data["plan_id"];
      plan_list.prepend(element);

      // update designation list
      element = document.createElement("option");
      element.selected = true;
      element.value = data["plan_id"];
      if (data["designation_id"] !== null) {
        element.innerText = data["plan_link"];
      } else {
        element.innerText = "-";
      }
      desgn_list.prepend(element);

      // update form operation-type + comment
      document.getElementById("div_check").checked = data.operation_types.div_check;
      document.getElementById("cad_check").checked = data.operation_types.cad_check;
      document.getElementById("serv_check").checked = data.operation_types.serv_check;
      document.getElementById("art35_check").checked = data.operation_types.art35_check;
      document.getElementById("other_check").checked = data.operation_types.other_check;
      document.getElementById("delayed_check").checked = data.plan_retarde;
      document.getElementById("complement").value = data.complement;


      ph.active_plan_link = document.getElementById("plan-link-continue").value;

      ph.showSuccessMessage(title="Succès !", body="✅ La saisie a bien été récupérée.");

    }).catch((err) => {
      alert('Une erreur s\'est produite. Veuillez contacter l\'administrateur\n\n \
    Détail de l\'erreur:\n' + String(err));
    });

    return;
}

ph.parcelState = (type) => {
  // Retriev selected lines in table(s)
  const source_table = document.getElementById('source_table');
  const dest_table = document.getElementById('destination_table');
  const selected_source_rows = source_table.getElementsByClassName("selected");
  const selected_dest_rows = dest_table.getElementsByClassName("selected");
  const types = {
    'origin': 'BF(s) originel(s)',
    'rp_in': 'Entré(s) RP',
    'rp_out': 'Sorti(s) RP',
    'final': 'Final-aux',
  };
  let source_bf_list = [];
  let dest_bf_list = [];
  for (let row of selected_source_rows) {
    source_bf_list.push(row.firstChild.innerText);
  }
  for (let row of selected_dest_rows) {
    dest_bf_list.push(row.firstChild.innerText);
  }
  if ((type === 'origin' || type === 'rp_out') && dest_bf_list > 0) {
    alert("Attention, cette action ne peut pas être utilisée avec des BFs qui n'ont pas d'enfants (liste pas prise en compte).")
  }
  if ((type === 'final' || type === 'rp_in') && source_bf_list > 0) {
    alert("Attention, cette action ne peut pas être utilisée avec des BFs qui n'ont pas de parents (liste pas prise en compte).")
  }

  if (window.confirm("Les BFs sélectionnés vont être traités (\""+types[type]+"\"). Êtes-vous sûr(e) ?")) {

    // Show overlay
    document.getElementById("overlay").style.display = "block";

    const params = {
      'type': type,
      'cadastre': ph.activecadastre,
      'source_bfs': source_bf_list,
      'dest_bfs': dest_bf_list
    };

    fetch('submit_control', {
      method: 'POST',
      headers: {
        'Accept': 'application/json, text/plain,  */*',
        'Content-Type': 'application/json'
      },
      headers: { 'X-CSRFToken': ph.csrftoken },
      mode: 'same-origin',
      body: JSON.stringify(params),
    })
    .then(res => res.json())
    .then(res => {
      // unselect rows, reload tables
      ph.run_control();
    });
  }
}

ph.showSuccessMessage = (title="Succès !", body="✅ La tâche a été exécutée avec succès.", delay=5000) => {
  const toastElement = document.getElementById('successToast');
  document.getElementById('successToastTitle').innerHTML = "<strong>" + title + "</strong>";
  document.getElementById('successToastBody').innerHTML = body;

  const toast = new bootstrap.Toast(toastElement, {
    delay: delay
  });

  toast.show();
}

ph.showErrorMessage = (title="Erreur !", body="❌ La tâche n'a pas été exécutée.", delay=5000) => {
  const toastElement = document.getElementById('errorToast');
  document.getElementById('errorToastTitle').innerHTML = "<strong>" + title + "</strong>";
  document.getElementById('errorToastBody').innerHTML = body;

  const toast = new bootstrap.Toast(toastElement, {
    delay: delay
  });

  toast.show();
}
