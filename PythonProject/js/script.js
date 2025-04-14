// Function to search a location
function searchLocation() {
    let location = document.getElementById("locationInput").value;
    if (location.trim() === "") {
        alert("Please enter a location!");
        return;
    }
    alert("Searching for traffic updates at " + location);
}

// Function to get user's GPS location
function getUserLocation() {
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            function(position) {
                let lat = position.coords.latitude;
                let lng = position.coords.longitude;
                alert("Your current location: Lat " + lat + ", Lng " + lng);
                updateMap(lat, lng);
            },
            function(error) {
                alert("Error getting location: " + error.message);
            }
        );
    } else {
        alert("Geolocation is not supported by your browser.");
    }
}

// Function to initialize Google Map
function initMap() {
    let map = new google.maps.Map(document.getElementById("map"), {
        center: { lat: 40.7128, lng: -74.0060 }, // Default: New York City
        zoom: 12
    });
}

// Function to update the map with user location
function updateMap(lat, lng) {
    let map = new google.maps.Map(document.getElementById("map"), {
        center: { lat: lat, lng: lng },
        zoom: 14
    });

    new google.maps.Marker({
        position: { lat: lat, lng: lng },
        map: map,
        title: "You are here"
    });
}

// Simulated updates for traffic status
function updateTrafficStatus() {
    document.getElementById("trafficStatus").innerText = "Moderate Traffic in City Center";
}

function updateEmergencyAlerts() {
    document.getElementById("emergencyAlerts").innerText = "Ambulance approaching Main Street!";
}

function updateTrafficLights() {
    document.getElementById("trafficLights").innerText = "Green lights optimized for smooth flow";
}

// Simulated data updates
setTimeout(updateTrafficStatus, 2000);
setTimeout(updateEmergencyAlerts, 4000);
setTimeout(updateTrafficLights, 6000);
