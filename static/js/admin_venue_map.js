(function () {
  function parseFloatOrNull(value) {
    var parsed = parseFloat(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function initVenueMap() {
    var mapEl = document.getElementById("venue-map");
    var searchInput = document.getElementById("venue-map-search");
    var searchBtn = document.getElementById("venue-map-search-btn");
    var latInput = document.getElementById("id_latitude");
    var lngInput = document.getElementById("id_longitude");

    if (!mapEl || !latInput || !lngInput || typeof L === "undefined") {
      return;
    }

    var initialLat = parseFloatOrNull(latInput.value);
    var initialLng = parseFloatOrNull(lngInput.value);
    var hasSavedLocation = initialLat !== null && initialLng !== null;
    var center = hasSavedLocation ? [initialLat, initialLng] : [27.7172, 85.324];
    var zoom = hasSavedLocation ? 14 : 12;

    var map = L.map(mapEl).setView(center, zoom);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);

    var marker = L.marker(center, { draggable: true }).addTo(map);
    var resultBox = document.createElement("div");
    resultBox.id = "venue-map-results";
    resultBox.style.marginTop = "8px";
    resultBox.style.maxHeight = "140px";
    resultBox.style.overflowY = "auto";
    resultBox.style.background = "#f8f8f8";
    resultBox.style.border = "1px solid #d9d9d9";
    resultBox.style.borderRadius = "6px";
    resultBox.style.padding = "6px";
    mapEl.parentNode.insertBefore(resultBox, mapEl.nextSibling);

    function updateInputs(latlng) {
      latInput.value = latlng.lat.toFixed(6);
      lngInput.value = latlng.lng.toFixed(6);
    }

    map.on("click", function (event) {
      marker.setLatLng(event.latlng);
      updateInputs(event.latlng);
    });

    marker.on("dragend", function () {
      updateInputs(marker.getLatLng());
    });

    function syncMarkerFromInputs() {
      var lat = parseFloatOrNull(latInput.value);
      var lng = parseFloatOrNull(lngInput.value);
      if (lat === null || lng === null) {
        return;
      }
      var latlng = L.latLng(lat, lng);
      marker.setLatLng(latlng);
      map.panTo(latlng);
    }

    latInput.addEventListener("change", syncMarkerFromInputs);
    lngInput.addEventListener("change", syncMarkerFromInputs);

    function moveToLocation(lat, lng, zoomLevel) {
      var latlng = L.latLng(lat, lng);
      marker.setLatLng(latlng);
      updateInputs(latlng);
      map.setView(latlng, zoomLevel || 15);
    }

    function clearResults() {
      resultBox.innerHTML = "";
    }

    function renderResults(results) {
      clearResults();
      if (!results.length) {
        resultBox.innerHTML = "<small>No location found.</small>";
        return;
      }

      results.forEach(function (item) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = item.display_name;
        btn.style.display = "block";
        btn.style.width = "100%";
        btn.style.textAlign = "left";
        btn.style.padding = "6px 8px";
        btn.style.marginBottom = "4px";
        btn.style.border = "1px solid #ddd";
        btn.style.background = "#fff";
        btn.style.color = "#111";
        btn.style.fontSize = "13px";
        btn.style.lineHeight = "1.3";
        btn.style.cursor = "pointer";
        btn.style.whiteSpace = "normal";
        btn.addEventListener("click", function () {
          moveToLocation(parseFloat(item.lat), parseFloat(item.lon), 16);
          clearResults();
        });
        btn.addEventListener("mouseenter", function () {
          btn.style.background = "#eef3ff";
        });
        btn.addEventListener("mouseleave", function () {
          btn.style.background = "#fff";
        });
        resultBox.appendChild(btn);
      });
    }

    function runSearch() {
      if (!searchInput) {
        return;
      }

      var query = searchInput.value.trim();
      if (!query) {
        clearResults();
        return;
      }

      var endpoint = "https://nominatim.openstreetmap.org/search?format=jsonv2&limit=5&q=" + encodeURIComponent(query);
      fetch(endpoint, {
        headers: {
          Accept: "application/json",
          "User-Agent": "EventMandu Admin/1.0",
        },
      })
        .then(function (response) {
          if (!response.ok) {
            throw new Error("Search request failed");
          }
          return response.json();
        })
        .then(function (data) {
          renderResults(Array.isArray(data) ? data : []);
        })
        .catch(function () {
          resultBox.innerHTML = "<small>Search failed. Try again.</small>";
        });
    }

    if (searchBtn) {
      searchBtn.addEventListener("click", runSearch);
    }

    if (searchInput) {
      searchInput.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          event.preventDefault();
          runSearch();
        }
      });
    }
  }

  document.addEventListener("DOMContentLoaded", initVenueMap);
})();
