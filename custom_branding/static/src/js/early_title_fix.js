/** @odoo-module **/

const BRAND = "Dreamwarez";

// 1. Set immediately
document.title = BRAND;

// 2. Aggressively fix during early loading (safe)
let attempts = 0;
const maxAttempts = 50; // ~2 seconds

const fixTitle = () => {
    if (document.title.includes("Odoo")) {
        document.title = BRAND;
    }
    attempts++;
    if (attempts >= maxAttempts) {
        clearInterval(timer);
    }
};

const timer = setInterval(fixTitle, 40);

// 3. Final safety once DOM is ready
window.addEventListener("DOMContentLoaded", () => {
    document.title = BRAND;
});
