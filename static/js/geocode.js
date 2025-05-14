


window.getCurrentLocation = function () {
    const deliveryField = document.querySelector('#id_delivery_address');
    const latField = document.querySelector('#id_dest_lat');
    const lonField = document.querySelector('#id_dest_lon');

    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(async function (position) {
            const lat = position.coords.latitude;
            const lon = position.coords.longitude;

            if (latField) latField.value = lat;
            if (lonField) lonField.value = lon;

            try {
                const response = await fetch(`https://maps.googleapis.com/maps/api/geocode/json?latlng=${lat},${lon}&key=***REMOVED***`);
                const data = await response.json();

                if (data.status === 'OK' && data.results.length > 0) {
                    const address = data.results[0].formatted_address;
                    if (deliveryField) deliveryField.value = address;
                } else {
                    alert("Could not retrieve address from Google Maps.");
                }
            } catch (error) {
                console.error("Error fetching address:", error);
            }

        }, function (error) {
            alert("Error getting location: " + error.message);
        });
    } else {
        alert("Geolocation not supported by your browser.");
    }
};

