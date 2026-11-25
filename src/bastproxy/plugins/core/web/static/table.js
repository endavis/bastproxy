// Sorts and filters a table in the browser when the whole result is on one page.
// The server's links and form do the work for a result of more than one page.
// Text is only read with textContent; no markup is ever built from it.
(function () {
  "use strict";

  function cellText(row, index) {
    var cell = row.cells[index];
    return cell ? cell.textContent : "";
  }

  function compareFor(index, numeric, descending) {
    return function (a, b) {
      var left = cellText(a, index);
      var right = cellText(b, index);
      var result;
      if (numeric) {
        var x = parseFloat(left);
        var y = parseFloat(right);
        var xBad = isNaN(x);
        var yBad = isNaN(y);
        if (xBad || yBad) {
          // rows without a number go last in either direction
          if (xBad && yBad) {
            return 0;
          }
          return xBad ? 1 : -1;
        }
        result = x - y;
      } else {
        result = left.toLowerCase() < right.toLowerCase() ? -1 : left.toLowerCase() > right.toLowerCase() ? 1 : 0;
      }
      return descending ? -result : result;
    };
  }

  function enhance(table) {
    if (Number(table.getAttribute("data-pages")) > 1) {
      return;
    }
    var head = table.tHead;
    var body = table.tBodies[0];
    if (!head || !head.rows.length || !body) {
      return;
    }
    var headers = Array.prototype.slice.call(head.rows[0].cells);
    var inputs = [];
    var sorted = { index: -1, descending: false };

    function applyFilters() {
      var wanted = inputs.map(function (input) {
        return input.value.toLowerCase();
      });
      Array.prototype.forEach.call(body.rows, function (row) {
        var show = wanted.every(function (text, index) {
          return text === "" || cellText(row, index).toLowerCase().indexOf(text) !== -1;
        });
        row.hidden = !show;
      });
    }

    headers.forEach(function (header, index) {
      header.addEventListener("click", function (event) {
        event.preventDefault();
        var type = header.getAttribute("data-type");
        var numeric = type === "int" || type === "float";
        var descending = sorted.index === index ? !sorted.descending : false;
        sorted = { index: index, descending: descending };
        var rows = Array.prototype.slice.call(body.rows);
        rows.sort(compareFor(index, numeric, descending));
        rows.forEach(function (row) {
          body.appendChild(row);
        });
      });
    });

    var filterRow = document.createElement("tr");
    headers.forEach(function (header) {
      var cell = document.createElement("th");
      var input = document.createElement("input");
      input.type = "search";
      input.setAttribute("aria-label", "filter " + header.textContent);
      input.addEventListener("input", applyFilters);
      cell.appendChild(input);
      filterRow.appendChild(cell);
      inputs.push(input);
    });
    head.appendChild(filterRow);
  }

  function init() {
    Array.prototype.forEach.call(document.querySelectorAll("table[data-pages]"), enhance);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
