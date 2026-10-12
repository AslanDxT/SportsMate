function togglePassword(id) {

    const input = document.getElementById(id);

    if (!input) {
        return;
    }

    if (input.type === "password") {
        input.type = "text";
    } else {
        input.type = "password";
    }
}


// Automatically hide flash messages
setTimeout(() => {

    const flashes = document.querySelectorAll(".flash");

    flashes.forEach((flash) => {

        flash.style.transition = "opacity 0.4s";
        flash.style.opacity = "0";

        setTimeout(() => {
            flash.remove();
        }, 400);

    });

}, 4000);


// Register service worker for PWA
if ("serviceWorker" in navigator) {

    window.addEventListener("load", () => {

        navigator.serviceWorker
            .register("/service-worker.js")
            .then(() => {
                console.log("SportsMate service worker registered.");
            })
            .catch((error) => {
                console.log(
                    "Service worker registration failed:",
                    error
                );
            });

    });

}


// Confirm destructive actions
document.addEventListener("submit", function (event) {

    const form = event.target;

    if (form.dataset.confirm) {

        const message =
            form.dataset.confirm;

        if (!confirm(message)) {
            event.preventDefault();
        }

    }

});