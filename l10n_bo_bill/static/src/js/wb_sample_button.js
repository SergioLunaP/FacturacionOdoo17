/** @odoo-module **/

import { useState } from "@odoo/owl";
import { Component } from "@odoo/owl";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { registry } from "@web/core/registry";

class WBSampleButton extends Component {
    setup() {
        this.state = useState({});
    }

    onClick() {
        console.log("WB Sample Button clicked!");
    }
}

WBSampleButton.template = "WBSampleButton";

ProductScreen.addControlButton({
    component: WBSampleButton,
    position: ["before", "OrderlineCustomerNoteButton"],
});

registry.category("pos_screens").add("WBSampleButton", WBSampleButton);
