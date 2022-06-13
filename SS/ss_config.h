/*
 * Licensed to the OpenAirInterface (OAI) Software Alliance under one or more
 * contributor license agreements.  See the NOTICE file distributed with
 * this work for additional information regarding copyright ownership.
 * The OpenAirInterface Software Alliance licenses this file to You under
 * the OAI Public License, Version 1.1  (the "License"); you may not use this file
 * except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.openairinterface.org/?page_id=698
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *-------------------------------------------------------------------------------
 * For more information about the OpenAirInterface (OAI) Software Alliance:
 *      conmnc_digit_lengtht@openairinterface.org
 */

/*! \file ss_config.h
* \brief System Simulator configuration struct definitions and function prototypes
* \author Anurag Asokan
* \date 2022
* \version 0.1
* \company Firecell
* \email: anurag.ashokan@firecell.io
*/

#ifndef __SS_CONFIG_H__
#define __SS_CONFIG_H__

typedef enum ss_mode {
  NO_SS   = 0,
  SS_VT   = 1,
  SS_VT_SRB,
  SS_NOVT
} ss_mode_e;

typedef struct ss_config_s {
  /** SS mode of operation */
  ss_mode_e mode;
  /** IP Address where the TTCN engine is running */
  const char* hostIp;
  /** SYS port number */
  int Sysport;
  /** SRB port number */
  int Srbport;
  /** VNG port number */
  int Vngport;
  /** State info */
  int State;
} ss_config_t;


#endif /** __SS_CONFIG_H__ */
/** @} */
