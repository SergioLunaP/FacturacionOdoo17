from odoo import http
from odoo.http import request
import json

class SyncProgressController(http.Controller):

    @http.route('/l10n_bo_bill/sync_progress', type='json', auth='user')
    def sync_progress(self, progress):
        # Aquí puedes manejar el progreso
        request.env['bus.bus'].sendone(
            (request.env.cr.dbname, 'sync_progress', request.env.user.partner_id.id),
            {'type': 'sync_progress', 'progress': progress}
        )
        return {'status': 'success', 'progress': progress}
