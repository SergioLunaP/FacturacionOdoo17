from odoo import models, api
import logging

_logger = logging.getLogger(__name__)

class Sincronizacion(models.Model):
    _name = 'l10n_bo_bill.sincronizacion'
    _description = 'Sincronización automática de datos'

    @api.model
    def ejecutar_sincronizacion_diaria(self):
        """Ejecuta todas las sincronizaciones definidas en el menú"""
        _logger.info("Iniciando sincronización diaria de datos")

        try:
            # Ejecutar cada función de sincronización, ajustando los nombres de modelo
            self.env['res.partner'].obtener_clientes_desde_api()
            
            self.env['l10n_bo_bill.leyenda_factura'].obtener_leyendas_desde_api()
            self.env['l10n_bo_bill.producto_servicio'].obtener_productos_desde_api()
            self.env['l10n_bo_bill.tipo_pago'].obtener_tipos_pago_desde_api()
            self.env['l10n_bo_bill.evento_significativo'].obtener_eventos_significativos_desde_api()
            self.env['l10n_bo_bill.motivo_anulacion'].obtener_motivos_anulacion_desde_api()
            self.env['l10n_bo_bill.pais_origen'].obtener_paises_origen_desde_api()
            self.env['l10n_bo_bill.tipos_factura'].obtener_tipos_factura_desde_api()
            self.env['l10n_bo_bill.tipos_documento_identidad'].obtener_tipos_documento_identidad_desde_api()
            self.env['l10n_bo_bill.tipos_documento_sector'].obtener_tipos_documento_sector_desde_api()
            self.env['l10n_bo_bill.tipos_emision'].obtener_tipos_emision_desde_api()
            self.env['l10n_bo_bill.tipos_habitacion'].obtener_tipos_habitacion_desde_api()
            self.env['l10n_bo_bill.unidades_medida'].obtener_unidades_medida_desde_api()
            self.env['product.template'].obtener_productos_desde_api()
            _logger.info("Sincronización diaria completada exitosamente")
        except Exception as e:
            _logger.error(f"Error durante la sincronización diaria: {e}")
            raise e
