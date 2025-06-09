from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError
from datetime import datetime
import json
import requests
import logging
import base64
from datetime import datetime
import pytz
from datetime import timedelta



_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_bo_cufd = fields.Text(string='CUFD Code')
    l10n_bo_selling_point = fields.Many2one('selling_point', string='Selling Point', readonly=True)
    l10n_bo_branch_office = fields.Many2one('branch_office', string='Branch Office', readonly=True)
    l10n_bo_emission_type = fields.Many2one('emission_types', string='Emission Type')
    qr_code = fields.Binary(string="QR Code", attachment=True, store=True)
    l10n_bo_document_status = fields.Many2one('document_status', string='Document Status')

    cafc = fields.Text(string='cafc', default='123')

    e_billing = fields.Boolean(string='Electronic Billing', default=False)
    representation_format = fields.Boolean('Graphic Representation Format', default=False)
    representation_size = fields.Boolean('Graphic Representation Size')

    is_drafted = fields.Boolean('Is Drafted', default=False)
    is_cancelled = fields.Boolean('Is Cancelled', default=False)
    is_confirmed = fields.Boolean('Is Confirmed', default=False)

    journal_type = fields.Char(string='Journal Type')
    inv_type = fields.Boolean(string='Invoice Type')
    total_conv = fields.Float(default=0.0)
    total_lit = fields.Char(string='Literal Total')

    invoice_event_id = fields.Many2one('invoice_event', string='Invoice Event')
    event_begin_date = fields.Datetime(string='Event Begin Date')
    event_end_date = fields.Datetime(string='Event End Date')
    manual_invoice_date = fields.Datetime(string='Manual Invoice Date')
    is_manual = fields.Boolean('Is Manual', default=False)
    invalid_nit = fields.Boolean('Invalid NIT', default=False)
    total_discount = fields.Float(default=0.0)
    invoice_caption = fields.Char(string='Invoice Caption')
    is_offline = fields.Boolean('Is Offline', default=False)

    dui = fields.Text('DUI')
    auth_number = fields.Text('Authorization Number')
    control_code = fields.Text('Control Code')

    dosage_id = fields.Many2one('invoice_dosage', string='Dosage')
    reversed_inv_id = fields.Many2one('cancelled_invoices', string='Reversed Invoice')
    with_tax = fields.Boolean(string='With Tax', default=True)
    page_break = fields.Boolean(string='Page Break', default=False)
    manual_usd_edit = fields.Boolean(string='Manual USD Edit', default=False)
    check_inv = fields.Boolean(string='Check Invoice', default=False)

    dosage_data_edit = fields.Boolean(string='Dosage Data Editable')
    cufd_cuf_edit = fields.Boolean(string='CUFD/CUF Editable')
    skip_e_invoice_flow = fields.Boolean(string='Skip E-Invoice Flow')
    token_check = fields.Integer(string='Token Status')
    invoice_mails = fields.Text(string='Emails to Send')
    
    
    ##--------------------------Para Usar--------------------------##
    l10n_bo_cuf = fields.Text(string='CUF Code')
    l10n_bo_invoice_number = fields.Text(string='Invoice Number', readonly=True)
    efact_control_code = fields.Text(string='Url', readonly=True)
    
    valid_nit = fields.Boolean(string='Valid NIT', default=True)
    montoGiftCard = fields.Text(string='montoGiftCard', default='')
    is_reverted = fields.Boolean('Is Reverted', default=False)
    payment_method_code = fields.Selection(selection='_get_payment_methods', string="Método de Pago", help="Selecciona el método de pago desde la API")
    url = fields.Text(string="URL")
    
    mostrar_boton_fin_contingencia = fields.Boolean(
        compute='_compute_mostrar_boton_fin_contingencia', store=False
    )
    
    
    def _compute_mostrar_boton_fin_contingencia(self):
        direccion_api = self.env['l10n_bo_bill.direccion_api'].search([('activo', '=', True)], limit=1)
        for rec in self:
            rec.mostrar_boton_fin_contingencia = direccion_api.contingencia if direccion_api else False

    
    def _get_api_url(self):
        direccion_apis = self.env['l10n_bo_bill.direccion_api'].search([('activo', '=', True)], limit=1)

        if not direccion_apis:
            raise UserError("No se encontró una configuración de la API activa.")
        
        if len(direccion_apis) > 1:
            raise UserError("Hay más de una dirección de API activa. Por favor, verifica la configuración.")

        return direccion_apis.url

    
    @api.model
    def _get_payment_methods(self):
        #Metodos de Pago
        api_url = self._get_api_url()
        url = f"{api_url}/parametro/metodo-pago"

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            metodos = response.json()

            if not isinstance(metodos, list):
                raise UserError("La API no devolvió una lista válida de métodos de pago.")

            return [
                (str(m.get("codigoClasificador")), f"{m.get('codigoClasificador')} - {m.get('descripcion', 'Sin descripción')}")
                for m in metodos if m.get("codigoClasificador")
            ]

        except requests.exceptions.RequestException as e:
            _logger.error(f"Error al obtener métodos de pago de la API: {e}")
            return []

    def envio_sfv(self):
        #Facturacion y verificacion de conexion
        _logger.info("Iniciando proceso de envío SFV para las siguientes facturas: %s", self.ids)
        direccion_api = self.env['l10n_bo_bill.direccion_api'].search([('activo', '=', True)], limit=1)
        if direccion_api:
            _logger.info("Dirección API: %s | Contingencia: %s", direccion_api.url, direccion_api.contingencia)
        else:
            _logger.warning("No hay API")

        # If Contingencia Activa
        if direccion_api and direccion_api.contingencia:
            _logger.info("----Contingencia activa----")
            self.action_envio_a_impuestos()
            return

        # Verificación normal si no hay contingencia
        _logger.info("----Verificando comunicación----")
        res = self.verificar_comunicacion()
        if res:
            _logger.info("----Sin Conexion - Wizard----")
            return res

        _logger.info("----Comunicación verificada----")
        self.action_envio_a_impuestos()


    def action_envio_a_impuestos(self):
        for factura in self:
            _logger.info(f"Datos de factura ID: {factura.id} - Número: {factura.name}")

            if factura.move_type != 'out_invoice':
                raise UserError("Solo se pueden emitir facturas de cliente.")

            partner = factura.partner_id
            if not partner.codigo_cliente or not partner.external_id:
                raise UserError("El cliente no tiene external id.")

            detalle = []
            for line in factura.invoice_line_ids:
                product = line.product_id
                if not product.external_id:
                    raise UserError(f"El producto '{product.name}' no tiene external id")

                detalle.append({
                    "idProducto": product.external_id,
                    "cantidad": str(line.quantity),
                    "montoDescuento": "0.0",
                    "precio": str(line.price_unit)
                })
                
            direccion_api = self.env['l10n_bo_bill.direccion_api'].search([('activo', '=', True)], limit=1)

            payload = {
                "usuario": partner.codigo_cliente,
                "idPuntoVenta": 1,
                "idCliente": partner.external_id,
                "nitInvalido": True,
                "codigoMetodoPago": int(factura.payment_method_code),
                "activo": not direccion_api.contingencia if direccion_api else True,
                "masivo": False,
                "detalle": detalle,
                "idSucursal": 1,
                "numeroFactura": None,
                "fechaHoraEmision": None,
                "cafc": False,
                "numeroTarjeta": None,
                "descuentoGlobal": None,
                "monGiftCard": None
            }

            api_url = self._get_api_url()
            url = f"{api_url}/factura/emitir-computarizada"

            _logger.info(f"URL de emisión: {url}")
            _logger.info(f"JSON enviado: {json.dumps(payload, indent=2)}")

            try:
                response = requests.post(url, json=payload, timeout=15)
                response.raise_for_status()
                data = response.json()

                _logger.info(f"Respuesta API: {json.dumps(data, indent=2)}")

                if not all(k in data for k in ('codigoEstado', 'cuf', 'numeroFactura', 'url')):
                    raise UserError("La respuesta de la API no contiene todos los campos necesarios.")

                query = """
                    UPDATE account_move
                    SET l10n_bo_cuf = %s,
                        l10n_bo_invoice_number = %s,
                        url = %s
                    WHERE id = %s;
                """
                self.env.cr.execute(query, (
                    data['cuf'],
                    str(data['numeroFactura']),
                    data['url'],
                    factura.id
                ))

                _logger.info(f"Factura {factura.name} emitida correctamente con número {data['numeroFactura']}")
                factura.action_post()

            except requests.exceptions.HTTPError as e:
                content = e.response.text if e.response else "Sin respuesta de la API"
                _logger.error(f"Error HTTP al emitir factura {factura.name}: {e} - Respuesta: {content}")
                raise UserError(f"Error HTTP {e.response.status_code}:\n{content}")

            except requests.exceptions.RequestException as e:
                _logger.error(f"Error de conexión al emitir factura {factura.name}: {e}")
                raise UserError(f"No se pudo emitir la factura: {e}")

        return True

    #Llamar Wizard Revertir factura
    def action_open_reversal_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Revertir Factura',
            'res_model': 'account.move.reversal',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_ids': self.ids,
                'active_model': 'account.move',
            }
        }

    def revertir_anulacion(self):
        for factura in self:
            if not factura.l10n_bo_cuf:
                raise UserError("La factura no tiene un CUF asignado.")

            payload = {
                "cuf": factura.l10n_bo_cuf,
                "idPuntoVenta": 1,
                "idSucursal": 1
            }

            api_url = self._get_api_url()
            url = f"{api_url}/factura/reversion-anular"

            try:
                response = requests.post(url, json=payload, timeout=10)
                response.raise_for_status()
                data = response.json()

                if data.get('codigoEstado') != "907":
                    raise UserError(f"No se confirmó la reversión en la API. Estado: {data.get('codigoEstado')}")

                # Actualizar bo_bill
                factura.write({
                    'is_cancelled': False,
                    'is_reverted': True
                })

                _logger.info(f"Reversión de anulación, factura {factura.name}.")

            except requests.exceptions.RequestException as e:
                _logger.error(f"Error al revertir la anulación de la factura {factura.name}: {e}")
                raise UserError(f"Error al revertir la anulación en la API: {e}")
        return True
    
    def action_download_invoice_pdf(self):
        #Descargar pdf factura
        if not self.l10n_bo_cuf or not self.l10n_bo_invoice_number:
            raise UserError(_("No hay CUF o número de factura disponible para esta factura."))

        direccion_api = self._get_api_url()  
        base_url = direccion_api

        if not base_url.startswith("http"):
            base_url = "http://" + base_url
        full_base_url = f"{base_url}/pdf/download"

        params = {
            'cufd': self.l10n_bo_cuf,
            'numeroFactura': self.l10n_bo_invoice_number
        }

        full_url = requests.Request('GET', full_base_url, params=params).prepare().url
        _logger.info("URL completa para la descarga del PDF: %s", full_url)

        try:
            response = requests.get(full_url)
            if response.status_code == 200:
                # Codificar el contenido binario del PDF a base64
                pdf_content = base64.b64encode(response.content)
                attachment = self.env['ir.attachment'].create({
                    'name': 'Factura-%s.pdf' % self.l10n_bo_invoice_number,
                    'type': 'binary',
                    'datas': pdf_content,
                    'res_model': 'account.move',
                    'res_id': self.id,
                    'mimetype': 'application/pdf',
                })
                return attachment.id
            else:
                _logger.error("Error al descargar el PDF. Código de estado: %s. Respuesta: %s", response.status_code, response.text)
                raise UserError(_("Error al descargar el PDF. Código de estado: %s" % response.status_code))
        except requests.exceptions.RequestException as e:
            raise UserError(_("Error al conectar con la API: %s" % e))
        
    def action_invoice_preview(self):
        #Previsualizacion Factura
        if not self.l10n_bo_cuf or not self.l10n_bo_invoice_number:
            raise UserError(_("No hay CUF o número de factura disponible para esta factura."))

        direccion_api = self._get_api_url()
        base_url = direccion_api
        if not base_url.startswith("http"):
            base_url = "http://" + base_url
        full_base_url = f"{base_url}/pdf/download"

        params = {
            'cufd': self.l10n_bo_cuf,
            'numeroFactura': self.l10n_bo_invoice_number
        }

        full_url = requests.Request('GET', full_base_url, params=params).prepare().url
        _logger.info("URL completa para la previsualización del PDF: %s", full_url)

        try:
            response = requests.get(full_url)
            if response.status_code == 200:
                pdf_content = base64.b64encode(response.content)
                
                attachment = self.env['ir.attachment'].create({
                    'name': 'Factura-%s.pdf' % self.l10n_bo_invoice_number,
                    'type': 'binary',
                    'datas': pdf_content,
                    'res_model': 'account.move',
                    'res_id': self.id,
                    'mimetype': 'application/pdf',
                })

                return {
                    'type': 'ir.actions.act_url',
                    'url': '/web/content/%s?download=false' % attachment.id,
                    'target': 'new',
                }
            else:
                _logger.error("Error al descargar el PDF. Código de estado: %s. Respuesta: %s", response.status_code, response.text)
                raise UserError(_("Error al descargar el PDF. Código de estado: %s" % response.status_code))
        except requests.exceptions.RequestException as e:
            raise UserError(_("Error al conectar con la API: %s" % e))
        
        
    def verificar_comunicacion(self):
        base_url = self._get_api_url()
        url = f"{base_url}/contingencia/verificar-comunicacion"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                try:
                    respuesta_json = response.json()
                    _logger.info("Respuesta de verificación de comunicación: %s", respuesta_json)

                    if respuesta_json.get("mensaje", "").lower() != "conexion exitosa":
                        return self.action_mostrar_wizard_contingencia()

                except json.JSONDecodeError:
                    _logger.warning("Respuesta inválida (no JSON), mostrando wizard.")
                    return self.action_mostrar_wizard_contingencia()
            else:
                _logger.error("Error al verificar la comunicación. Código: %s. Respuesta: %s", response.status_code, response.text)
                return self.action_mostrar_wizard_contingencia()

        except requests.exceptions.RequestException as e:
            _logger.error("Error al conectar con la API de contingencia: %s", e)
            return self.action_mostrar_wizard_contingencia()
        
          
        
    def action_mostrar_wizard_contingencia(self):
        return {
            'name': 'Confirmar inicio de contingencia',
            'type': 'ir.actions.act_window',
            'res_model': 'contingencia.inicio.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id
            }
        }

            
    def action_download_invoice_pdf_true(self):
        """Función para descargar el PDF de la factura desde la API."""
        if not self.l10n_bo_cuf or not self.l10n_bo_invoice_number:
            raise UserError(_("No hay CUF o número de factura disponible para esta factura."))

        direccion_api = self._get_api_url()  
        base_url = direccion_api
        
        if not base_url.startswith("http"):
            base_url = "http://" + base_url

        full_base_url = f"{base_url}/pdf/download"

        params = {
            'cufd': self.l10n_bo_cuf,
            'numeroFactura': self.l10n_bo_invoice_number
        }

        full_url = requests.Request('GET', full_base_url, params=params).prepare().url
        _logger.info("URL completa para la descarga del PDF: %s", full_url)

        try:
            response = requests.get(full_url)

            if response.status_code == 200:
                pdf_content = base64.b64encode(response.content)

                attachment = self.env['ir.attachment'].create({
                    'name': 'Factura-%s.pdf' % self.l10n_bo_invoice_number,
                    'type': 'binary',
                    'datas': pdf_content,
                    'res_model': 'account.move',
                    'res_id': self.id,
                    'mimetype': 'application/pdf',
                })

                return {
                    'type': 'ir.actions.act_url',
                    'url': '/web/content/%s?download=true' % attachment.id,
                    'target': 'new',
                }
            else:
                _logger.error("Error al descargar el PDF. Código de estado: %s. Respuesta: %s", response.status_code, response.text)
                raise UserError(_("Error al descargar el PDF. Código de estado: %s" % response.status_code))
        except requests.exceptions.RequestException as e:
            raise UserError(_("Error al conectar con la API: %s" % e))
        
    def abrir_url(self):
        """Abre la URL almacenada en el campo url del registro"""
        for record in self:
            if record.url:
                return {
                    'type': 'ir.actions.act_url',
                    'url': record.url,
                    'target': 'new', 
                }
            else:
                raise UserError("No hay una URL definida para este registro.")
    
    
    def fin_de_contingencia(self):
        _logger.info("Iniciando proceso para finalizar la contingencia.")
        direccion_api = self.env['l10n_bo_bill.direccion_api'].search([('activo', '=', True)], limit=1)

        if not direccion_api or not direccion_api.contingencia:
            raise UserError("No hay contingencia activa registrada.")

        evento_id = direccion_api.evento_id
        if not evento_id:
            raise UserError("No se encontró un ID de evento para finalizar la contingencia.")

        api_url = self._get_api_url()
        url = f"{api_url}/contingencia/registrar-fin-evento/{evento_id}"

        _logger.info(f"Enviando solicitud para finalizar contingencia a: {url}")

        try:
            response = requests.post(url, timeout=60)
            response.raise_for_status()
            data = response.json()
            _logger.info(f"Respuesta finalización contingencia: {data}")

            # Validar mensaje
            mensaje = data.get("mensaje", "").lower()
            if "evento registrado con exito" not in mensaje:
                _logger.warning(f"La API no confirmó el final de la contingencia: {data}")
                raise UserError(f"No se confirmó la finalización de la contingencia: {data}")

            # Limpiar estado de contingencia
            direccion_api.write({
                'contingencia': False,
                'evento_id': None
            })
            _logger.info("✅ Contingencia desactivada correctamente.")

            #Emitir paquete
            emitir_url = f"{api_url}/factura/emitir-paquete/1/1/{evento_id}"
            _logger.info(f"Emitiendo paquete tras finalizar contingencia: {emitir_url}")
            emitir_response = requests.post(emitir_url, timeout=60)
            emitir_response.raise_for_status()
            emitir_data = emitir_response.json()
            _logger.info(f"Respuesta de emisión de paquete: {emitir_data}")

        except requests.exceptions.RequestException as e:
            _logger.error(f"Error al finalizar contingencia o emitir paquete: {e}")
            raise UserError(f"No se pudo finalizar la contingencia ni emitir el paquete:\n{e}")
        
    @api.model
    def finalizar_contingencia_automatica(self):
        """Finaliza automáticamente la contingencia si sigue activa"""
        direccion_api = self.env['l10n_bo_bill.direccion_api'].search([('activo', '=', True)], limit=1)
        if direccion_api and direccion_api.contingencia:
            _logger.info("Finalizando contingencia automáticamente (por cron)")
            return self.env['account.move'].fin_de_contingencia()
        _logger.info("No hay contingencia activa, no se realiza acción.")
        return True
