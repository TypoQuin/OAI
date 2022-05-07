#include "PHY/defs_gNB.h"
#include "PHY/NR_TRANSPORT/nr_transport_proto.h"
#include "PHY/LTE_REFSIG/lte_refsig.h"
#include "PHY/NR_REFSIG/nr_refsig.h"
#include "PHY/sse_intrin.h"

//#define DEBUG_PRS_MOD
//#define DEBUG_PRS_MAP

extern short nr_qpsk_mod_table[8];

int nr_generate_prs(uint32_t **nr_gold_prs,
                          int32_t *txdataF,
                          int16_t amp,
                          prs_data_t *prs_data,
                          nfapi_nr_config_request_scf_t *config,
                          NR_DL_FRAME_PARMS *frame_parms) {
  
  
  // Get K_Prime from the table for the length of PRS or LPRS
  int k_prime_table[4][12] = {
        {0,1,0,1,0,1,0,1,0,1,0,1},
        {0,2,1,3,0,2,1,3,0,2,1,3},
        {0,3,1,4,2,5,0,3,1,4,2,5},
        {0,6,3,9,1,7,4,10,2,8,5,11}};
    
  int k_prime = 0;
  int k=0;
  int16_t mod_prs[NR_MAX_PRS_LENGTH<<1];
  uint8_t idx=prs_data->NPRSID;
  
   // PRS resource mapping with combsize=k which means PRS symbols exist in every k-th subcarrier in frequency domain
   // According to ts138.211 sec.7.4.1.7.2
  for (int l = prs_data->SymbolStart; l < prs_data->SymbolStart + prs_data->NumPRSSymbols; l++) {

    int symInd = l-prs_data->SymbolStart;
    if (prs_data->CombSize == 2) {
      k_prime = k_prime_table[0][symInd];
    }
    else if (prs_data->CombSize == 4){
      k_prime = k_prime_table[1][symInd];
    }
    else if (prs_data->CombSize == 6){
      k_prime = k_prime_table[2][symInd];
    }
    else if (prs_data->CombSize == 12){
      k_prime = k_prime_table[3][symInd];
    }
    
    k = (prs_data->REOffset+k_prime) % prs_data->CombSize + prs_data->RBOffset*12 + frame_parms->first_carrier_offset;
    
    // QPSK modulation
    for (int m = 0; m < (12/prs_data->CombSize) * prs_data->NumRB; m++) {
      idx = (((nr_gold_prs[l][(m<<1)>>5])>>((m<<1)&0x1f))&3);
      mod_prs[m<<1] = nr_qpsk_mod_table[idx<<1];
      mod_prs[(m<<1)+1] = nr_qpsk_mod_table[(idx<<1) + 1];
      
#ifdef DEBUG_PRS_MOD
      LOG_D("m %d idx %d gold seq %d mod_prs %d %d\n", m, idx, nr_gold_prs[l][(m<<1)>>5], mod_prs[m<<1], mod_prs[(m<<1)+1]);
#endif
      
#ifdef DEBUG_PRS_MAP
      LOG_D("m %d at k %d of l %d reIdx %d\n", m, k, l, (l*frame_parms->ofdm_symbol_size + k)<<1);
#endif
      
      ((int16_t *)txdataF)[(l*frame_parms->ofdm_symbol_size + k)<<1]       = (amp * mod_prs[m<<1]) >> 15;
      ((int16_t *)txdataF)[((l*frame_parms->ofdm_symbol_size + k)<<1) + 1] = (amp * mod_prs[(m<<1) + 1]) >> 15;
    
#ifdef DEBUG_PRS_MAP
      LOG_D("(%d,%d)\n",
      ((int16_t *)txdataF)[(l*frame_parms->ofdm_symbol_size + k)<<1],
      ((int16_t *)txdataF)[((l*frame_parms->ofdm_symbol_size + k)<<1)+1]);
#endif

      k = k +  prs_data->CombSize;
    
      if (k >= frame_parms->ofdm_symbol_size)
        k-=frame_parms->ofdm_symbol_size;
      }
  }
#ifdef DEBUG_PRS_MAP
  LOG_M("nr_prs.m", "prs",(int16_t *)&txdataF[prs_data->SymbolStart*frame_parms->ofdm_symbol_size],prs_data->NumPRSSymbols*frame_parms->ofdm_symbol_size, 1, 1);
#endif
  return 0;
}