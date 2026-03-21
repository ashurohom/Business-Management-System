odoo.define('custom_branding.custom_content', function (require) {
    "use strict";
    console.log("Custom Branding JS loaded");

    setInterval(function () {
        document.title = document.title.replace('Odoo', 'Dreamwarez');
    }, 100);
});
