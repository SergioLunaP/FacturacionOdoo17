/** @odoo-module **/

import { useState } from "@odoo/owl";
import { useBus } from "@web/core/utils/hooks";
import { Component } from "@odoo/owl";

// Resto del código...

class ProgressModalComponent extends Component {
    setup() {
        this.state = useState({ progress: 0, isVisible: false });

        // Suscríbete al evento 'sync_progress' del bus
        useBus(this.env.bus, "sync_progress", this.updateProgress);
    }

    updateProgress({ progress }) {
        // Si el progreso es 0, muestra el modal; si es 100, ocúltalo
        if (progress === 0) {
            this.state.isVisible = true;
        } else if (progress === 100) {
            this.state.isVisible = false;
        }
        this.state.progress = progress;
    }
}

ProgressModalComponent.template = "l10n_bo_bill.ProgressModalTemplate";

export default ProgressModalComponent;
