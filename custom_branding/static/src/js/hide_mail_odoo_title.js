/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Dialog } from "@web/core/dialog/dialog";

patch(Dialog.prototype, {
    setup() {
        super.setup();

        
        if (this.props.title === "Odoo") {
            this.props.title = "DREAMWAREZ";
        }
    },
});
