/*******************************************************************************
    OpenAirInterface
    Copyright(c) 1999 - 2014 Eurecom

    OpenAirInterface is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.


    OpenAirInterface is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with OpenAirInterface.The full GNU General Public License is
    included in this distribution in the file called "COPYING". If not,
    see <http://www.gnu.org/licenses/>.

  Contact Information
  OpenAirInterface Admin: openair_admin@eurecom.fr
  OpenAirInterface Tech : openair_tech@eurecom.fr
  OpenAirInterface Dev  : openair4g-devel@lists.eurecom.fr

  Address      : Eurecom, Campus SophiaTech, 450 Route des Chappes, CS 50193 - 06904 Biot Sophia Antipolis cedex, FRANCE

 *******************************************************************************/

/*
                                play_scenario.c
                                -------------------
  AUTHOR  : Lionel GAUTHIER
  COMPANY : EURECOM
  EMAIL   : Lionel.Gauthier@eurecom.fr
 */

#include <string.h>
#include <limits.h>
#include <libconfig.h>
#include <inttypes.h>
#include <getopt.h>
#include <libgen.h>
#include <unistd.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <unistd.h>


#include "intertask_interface_init.h"
#include "timer.h"
#include "assertions.h"
#include "s1ap_common.h"
#include "intertask_interface.h"
#include "play_scenario.h"
#include "sctp_eNB_task.h"
#include "log.h"
//------------------------------------------------------------------------------
#define PLAY_SCENARIO              1
#define GS_IS_FILE                 1
#define GS_IS_DIR                  2
//------------------------------------------------------------------------------
char                  *g_openair_dir        = NULL;
//------------------------------------------------------------------------------
extern int                    xmlLoadExtDtdDefaultValue;
extern int                    asn_debug;
extern int                    asn1_xer_print;


//------------------------------------------------------------------------------
// test if file exist in current directory
int is_file_exists( const char const * file_nameP, const char const *file_roleP)
{
  struct stat s;
  int err = stat(file_nameP, &s);
  if(-1 == err) {
    if(ENOENT == errno) {
      fprintf(stderr, "Please provide a valid %s, %s does not exist\n", file_roleP, file_nameP);
    } else {
      perror("stat");
      exit(1);
    }
  } else {
    if(S_ISREG(s.st_mode)) {
      return GS_IS_FILE;
    } else if(S_ISDIR(s.st_mode)) {
      return GS_IS_DIR;
    } else {
      fprintf(stderr, "Please provide a valid test %s, %s exists but is not found valid\n", file_roleP, file_nameP);
    }
  }
  return 0;
}


//------------------------------------------------------------------------------
int et_strip_extension(char *in_filename)
{
  static const uint8_t name_min_len = 1;
  static const uint8_t max_ext_len = 5; // .pdml !
  fprintf(stdout, "strip_extension %s\n", in_filename);

  if (NULL != in_filename) {
    /* Check chars starting at end of string to find last '.' */
    for (ssize_t i = strlen(in_filename); i > (name_min_len + max_ext_len); i--) {
      if (in_filename[i] == '.') {
        in_filename[i] = '\0';
        return i;
      }
    }
  }
  return -1;
}
//------------------------------------------------------------------------------
// return number of splitted items
int split_path( char * pathP, char *** resP)
{
  char *  saveptr1;
  char *  p    = strtok_r (pathP, "/", &saveptr1);
  int     n_spaces = 0;

  /// split string and append tokens to 'res'
  while (p) {
    *resP = realloc (*resP, sizeof (char*) * ++n_spaces);
    AssertFatal (*resP, "realloc failed");
    (*resP)[n_spaces-1] = p;
    p = strtok_r (NULL, "/", &saveptr1);
  }
  return n_spaces;
}
//------------------------------------------------------------------------------
void et_free_packet(et_packet_t* packet)
{
  if (packet) {
    switch (packet->sctp_hdr.chunk_type) {
      case SCTP_CID_DATA:
        et_free_pointer(packet->sctp_hdr.u.data_hdr.payload.binary_stream);
        break;
      default:
        ;
    }
    et_free_pointer(packet);
  }
}

//------------------------------------------------------------------------------
void et_free_scenario(et_scenario_t* scenario)
{
  et_packet_t *packet = NULL;
  et_packet_t *next_packet = NULL;
  if (scenario) {
    packet = scenario->list_packet;
    while (packet) {
      next_packet = packet->next;
      et_free_packet(packet);
      packet = next_packet->next;
    }
    et_free_pointer(scenario);
  }
}

//------------------------------------------------------------------------------
char * et_ip2ip_str(const et_ip_t * const ip)
{
  static char str[INET6_ADDRSTRLEN];

  sprintf(str, "ERROR");
  switch (ip->address_family) {
    case AF_INET6:
      inet_ntop(AF_INET6, &(ip->address.ipv6), str, INET6_ADDRSTRLEN);
      break;
    case AF_INET:
      inet_ntop(AF_INET, &(ip->address.ipv4), str, INET_ADDRSTRLEN);
      break;
    default:
      ;
  }
  return str;
}
//------------------------------------------------------------------------------
//convert hexstring to len bytes of data
//returns 0 on success, negative on error
//data is a buffer of at least len bytes
//hexstring is upper or lower case hexadecimal, NOT prepended with "0x"
int et_hex2data(unsigned char * const data, const unsigned char * const hexstring, const unsigned int len)
{
  unsigned const char *pos = hexstring;
  char *endptr = NULL;
  size_t count = 0;

  fprintf(stdout, "%s(%s,%d)\n", __FUNCTION__, hexstring, len);

  if ((len > 1) && (strlen((const char*)hexstring) % 2)) {
    //or hexstring has an odd length
    return -3;
  }

  if (len == 1)  {
    char buf[5] = {'0', 'x', 0, pos[0], '\0'};
    data[0] = strtol(buf, &endptr, 16);
    /* Check for various possible errors */
    AssertFatal ((errno == 0) || (data[0] != 0), "ERROR %s() strtol: %s\n", __FUNCTION__, strerror(errno));
    AssertFatal (endptr != buf, "ERROR %s() No digits were found\n", __FUNCTION__);
    return 0;
  }

  for(count = 0; count < len/2; count++) {
    char buf[5] = {'0', 'x', pos[0], pos[1], 0};
    data[count] = strtol(buf, &endptr, 16);
    pos += 2 * sizeof(char);
    AssertFatal (endptr[0] == '\0', "ERROR %s() non-hexadecimal character encountered buf %p endptr %p buf %s count %zu pos %p\n", __FUNCTION__, buf, endptr, buf, count, pos);
    AssertFatal (endptr != buf, "ERROR %s() No digits were found\n", __FUNCTION__);
  }
  return 0;
}
//------------------------------------------------------------------------------
sctp_cid_t et_chunk_type_str2cid(const xmlChar * const chunk_type_str)
{
  if ((!xmlStrcmp(chunk_type_str, (const xmlChar *)"DATA")))              { return SCTP_CID_DATA;}
  if ((!xmlStrcmp(chunk_type_str, (const xmlChar *)"INIT")))              { return SCTP_CID_INIT;}
  if ((!xmlStrcmp(chunk_type_str, (const xmlChar *)"INIT_ACK")))          { return SCTP_CID_INIT_ACK;}
  if ((!xmlStrcmp(chunk_type_str, (const xmlChar *)"SACK")))              { return SCTP_CID_SACK;}
  if ((!xmlStrcmp(chunk_type_str, (const xmlChar *)"HEARTBEAT")))         { return SCTP_CID_HEARTBEAT;}
  if ((!xmlStrcmp(chunk_type_str, (const xmlChar *)"HEARTBEAT_ACK")))     { return SCTP_CID_HEARTBEAT_ACK;}
  if ((!xmlStrcmp(chunk_type_str, (const xmlChar *)"ABORT")))             { return SCTP_CID_ABORT;}
  if ((!xmlStrcmp(chunk_type_str, (const xmlChar *)"SHUTDOWN")))          { return SCTP_CID_SHUTDOWN;}
  if ((!xmlStrcmp(chunk_type_str, (const xmlChar *)"SHUTDOWN_ACK")))      { return SCTP_CID_SHUTDOWN_ACK;}
  if ((!xmlStrcmp(chunk_type_str, (const xmlChar *)"ERROR")))             { return SCTP_CID_ERROR;}
  if ((!xmlStrcmp(chunk_type_str, (const xmlChar *)"COOKIE_ECHO")))       { return SCTP_CID_COOKIE_ECHO;}
  if ((!xmlStrcmp(chunk_type_str, (const xmlChar *)"COOKIE_ACK")))        { return SCTP_CID_COOKIE_ACK;}
  if ((!xmlStrcmp(chunk_type_str, (const xmlChar *)"ECN_ECNE")))          { return SCTP_CID_ECN_ECNE;}
  if ((!xmlStrcmp(chunk_type_str, (const xmlChar *)"ECN_CWR")))           { return SCTP_CID_ECN_CWR;}
  if ((!xmlStrcmp(chunk_type_str, (const xmlChar *)"SHUTDOWN_COMPLETE"))) { return SCTP_CID_SHUTDOWN_COMPLETE;}
  if ((!xmlStrcmp(chunk_type_str, (const xmlChar *)"AUTH")))              { return SCTP_CID_AUTH;}
  if ((!xmlStrcmp(chunk_type_str, (const xmlChar *)"FWD_TSN")))           { return SCTP_CID_FWD_TSN;}
  if ((!xmlStrcmp(chunk_type_str, (const xmlChar *)"ASCONF")))            { return SCTP_CID_ASCONF;}
  if ((!xmlStrcmp(chunk_type_str, (const xmlChar *)"ASCONF_ACK")))        { return SCTP_CID_ASCONF_ACK;}
  AssertFatal (0, "ERROR: %s() cannot convert: %s\n", __FUNCTION__, chunk_type_str);
}
//------------------------------------------------------------------------------
const char * const et_chunk_type_cid2str(const sctp_cid_t chunk_type)
{
  switch (chunk_type) {
    case  SCTP_CID_DATA:              return "DATA"; break;
    case  SCTP_CID_INIT:              return "INIT"; break;
    case  SCTP_CID_INIT_ACK:          return "INIT_ACK"; break;
    case  SCTP_CID_SACK:              return "SACK"; break;
    case  SCTP_CID_HEARTBEAT:         return "HEARTBEAT"; break;
    case  SCTP_CID_HEARTBEAT_ACK:     return "HEARTBEAT_ACK"; break;
    case  SCTP_CID_ABORT:             return "ABORT"; break;
    case  SCTP_CID_SHUTDOWN:          return "SHUTDOWN"; break;
    case  SCTP_CID_SHUTDOWN_ACK:      return "SHUTDOWN_ACK"; break;
    case  SCTP_CID_ERROR:             return "ERROR"; break;
    case  SCTP_CID_COOKIE_ECHO:       return "COOKIE_ECHO"; break;
    case  SCTP_CID_COOKIE_ACK:        return "COOKIE_ACK"; break;
    case  SCTP_CID_ECN_ECNE:          return "ECN_ECNE"; break;
    case  SCTP_CID_ECN_CWR:           return "ECN_CWR"; break;
    case  SCTP_CID_SHUTDOWN_COMPLETE: return "SHUTDOWN_COMPLETE"; break;
    case  SCTP_CID_AUTH:              return "AUTH"; break;
    case  SCTP_CID_FWD_TSN:           return "FWD_TSN"; break;
    case  SCTP_CID_ASCONF:            return "ASCONF"; break;
    case  SCTP_CID_ASCONF_ACK:        return "ASCONF_ACK"; break;
    default:
      AssertFatal (0, "ERROR %s(): Unknown chunk_type %d!\n", __FUNCTION__, chunk_type);
  }
}
//------------------------------------------------------------------------------
et_packet_action_t et_action_str2et_action_t(const xmlChar * const action)
{
  if ((!xmlStrcmp(action, (const xmlChar *)"SEND")))              { return ET_PACKET_ACTION_S1C_SEND;}
  if ((!xmlStrcmp(action, (const xmlChar *)"RECEIVE")))              { return ET_PACKET_ACTION_S1C_RECEIVE;}
  AssertFatal (0, "ERROR: %s cannot convert: %s\n", __FUNCTION__, action);
  //if (NULL == action) {return ACTION_S1C_NULL;}
}
//------------------------------------------------------------------------------
void et_ip_str2et_ip(const xmlChar  * const ip_str, et_ip_t * const ip)
{
  AssertFatal (NULL != ip_str, "ERROR %s() Cannot convert null string to ip address!\n", __FUNCTION__);
  AssertFatal (NULL != ip,     "ERROR %s() out parameter pointer is NULL!\n", __FUNCTION__);
  // store this IP address in sa:
  if (inet_pton(AF_INET, (const char*)ip_str, (void*)&(ip->address.ipv4)) > 0) {
    ip->address_family = AF_INET;
  } else if (inet_pton(AF_INET6, (const char*)ip_str, (void*)&(ip->address.ipv6)) > 0) {
    ip->address_family = AF_INET6;
  } else {
    ip->address_family = AF_UNSPEC;
    AssertFatal (0, "ERROR %s() Could not parse ip address %s!\n", __FUNCTION__, ip_str);
  }
}
/*------------------------------------------------------------------------------*/
uint32_t et_eNB_app_register(const Enb_properties_array_t *enb_properties)
{
  uint32_t         enb_id;
  uint32_t         mme_id;
  MessageDef      *msg_p;
  uint32_t         register_enb_pending = 0;
  char            *str                  = NULL;
  struct in_addr   addr;


  for (enb_id = 0; (enb_id < enb_properties->number) ; enb_id++) {
    {
      s1ap_register_enb_req_t *s1ap_register_eNB;

      /* note:  there is an implicit relationship between the data structure and the message name */
      msg_p = itti_alloc_new_message (TASK_ENB_APP, S1AP_REGISTER_ENB_REQ);

      s1ap_register_eNB = &S1AP_REGISTER_ENB_REQ(msg_p);

      /* Some default/random parameters */
      s1ap_register_eNB->eNB_id           = enb_properties->properties[enb_id]->eNB_id;
      s1ap_register_eNB->cell_type        = enb_properties->properties[enb_id]->cell_type;
      s1ap_register_eNB->eNB_name         = enb_properties->properties[enb_id]->eNB_name;
      s1ap_register_eNB->tac              = enb_properties->properties[enb_id]->tac;
      s1ap_register_eNB->mcc              = enb_properties->properties[enb_id]->mcc;
      s1ap_register_eNB->mnc              = enb_properties->properties[enb_id]->mnc;
      s1ap_register_eNB->mnc_digit_length = enb_properties->properties[enb_id]->mnc_digit_length;
      s1ap_register_eNB->default_drx      = enb_properties->properties[enb_id]->pcch_defaultPagingCycle[0];

      s1ap_register_eNB->nb_mme =         enb_properties->properties[enb_id]->nb_mme;
      AssertFatal (s1ap_register_eNB->nb_mme <= S1AP_MAX_NB_MME_IP_ADDRESS, "Too many MME for eNB %d (%d/%d)!", enb_id, s1ap_register_eNB->nb_mme,
                   S1AP_MAX_NB_MME_IP_ADDRESS);

      for (mme_id = 0; mme_id < s1ap_register_eNB->nb_mme; mme_id++) {
        s1ap_register_eNB->mme_ip_address[mme_id].ipv4 = enb_properties->properties[enb_id]->mme_ip_address[mme_id].ipv4;
        s1ap_register_eNB->mme_ip_address[mme_id].ipv6 = enb_properties->properties[enb_id]->mme_ip_address[mme_id].ipv6;
        strncpy (s1ap_register_eNB->mme_ip_address[mme_id].ipv4_address,
                 enb_properties->properties[enb_id]->mme_ip_address[mme_id].ipv4_address,
                 sizeof(s1ap_register_eNB->mme_ip_address[0].ipv4_address));
        strncpy (s1ap_register_eNB->mme_ip_address[mme_id].ipv6_address,
                 enb_properties->properties[enb_id]->mme_ip_address[mme_id].ipv6_address,
                 sizeof(s1ap_register_eNB->mme_ip_address[0].ipv6_address));
      }

      s1ap_register_eNB->sctp_in_streams       = enb_properties->properties[enb_id]->sctp_in_streams;
      s1ap_register_eNB->sctp_out_streams      = enb_properties->properties[enb_id]->sctp_out_streams;


      s1ap_register_eNB->enb_ip_address.ipv6 = 0;
      s1ap_register_eNB->enb_ip_address.ipv4 = 1;
      addr.s_addr = enb_properties->properties[enb_id]->enb_ipv4_address_for_S1_MME;
      str = inet_ntoa(addr);
      strcpy(s1ap_register_eNB->enb_ip_address.ipv4_address, str);

      itti_send_msg_to_task (TASK_S1AP, ENB_MODULE_ID_TO_INSTANCE(enb_id), msg_p);

      register_enb_pending++;
    }
  }

  return register_enb_pending;
}
/*------------------------------------------------------------------------------*/
void *et_eNB_app_task(void *args_p)
{
  const Enb_properties_array_t   *enb_properties_p  = NULL;
  uint32_t                        register_enb_pending;
  uint32_t                        registered_enb;
  long                            enb_register_retry_timer_id;
  uint32_t                        enb_id;
  MessageDef                     *msg_p           = NULL;
  const char                     *msg_name        = NULL;
  instance_t                      instance;
  int                             result;

  itti_mark_task_ready (TASK_ENB_APP);


  enb_properties_p = enb_config_get();


  /* Try to register each eNB */
  registered_enb = 0;
  register_enb_pending = et_eNB_app_register (enb_properties_p);


  do {
    // Wait for a message
    itti_receive_msg (TASK_ENB_APP, &msg_p);

    msg_name = ITTI_MSG_NAME (msg_p);
    instance = ITTI_MSG_INSTANCE (msg_p);

    switch (ITTI_MSG_ID(msg_p)) {
    case TERMINATE_MESSAGE:
      itti_exit_task ();
      break;



    case S1AP_REGISTER_ENB_CNF:
      LOG_I(ENB_APP, "[eNB %d] Received %s: associated MME %d\n", instance, msg_name,
            S1AP_REGISTER_ENB_CNF(msg_p).nb_mme);

      DevAssert(register_enb_pending > 0);
      register_enb_pending--;

      /* Check if at least eNB is registered with one MME */
      if (S1AP_REGISTER_ENB_CNF(msg_p).nb_mme > 0) {
        registered_enb++;
      }

      /* Check if all register eNB requests have been processed */
      if (register_enb_pending == 0) {
        if (registered_enb == enb_properties_p->number) {
          /* If all eNB are registered, start scenario */

        } else {
          uint32_t not_associated = enb_properties_p->number - registered_enb;

          LOG_W(ENB_APP, " %d eNB %s not associated with a MME, retrying registration in %d seconds ...\n",
                not_associated, not_associated > 1 ? "are" : "is", ET_ENB_REGISTER_RETRY_DELAY);

          /* Restart the eNB registration process in ENB_REGISTER_RETRY_DELAY seconds */
          if (timer_setup (ET_ENB_REGISTER_RETRY_DELAY, 0, TASK_ENB_APP, INSTANCE_DEFAULT, TIMER_ONE_SHOT,
                           NULL, &enb_register_retry_timer_id) < 0) {
            LOG_E(ENB_APP, " Can not start eNB register retry timer, use \"sleep\" instead!\n");

            sleep(ET_ENB_REGISTER_RETRY_DELAY);
            /* Restart the registration process */
            registered_enb = 0;
            register_enb_pending = et_eNB_app_register (enb_properties_p);
          }
        }
      }

      break;

    case S1AP_DEREGISTERED_ENB_IND:
      LOG_W(ENB_APP, "[eNB %d] Received %s: associated MME %d\n", instance, msg_name,
            S1AP_DEREGISTERED_ENB_IND(msg_p).nb_mme);

      /* TODO handle recovering of registration */
      break;

    case TIMER_HAS_EXPIRED:
      LOG_I(ENB_APP, " Received %s: timer_id %d\n", msg_name, TIMER_HAS_EXPIRED(msg_p).timer_id);

      if (TIMER_HAS_EXPIRED (msg_p).timer_id == enb_register_retry_timer_id) {
        /* Restart the registration process */
        registered_enb = 0;
        register_enb_pending = et_eNB_app_register (enb_properties_p);
      }
      break;

    default:
      LOG_E(ENB_APP, "Received unexpected message %s\n", msg_name);
      break;
    }

    result = itti_free (ITTI_MSG_ORIGIN_ID(msg_p), msg_p);
    AssertFatal (result == EXIT_SUCCESS, "Failed to free memory (%d)!\n", result);
  } while (1);
  return NULL;
}

//------------------------------------------------------------------------------
int et_play_scenario(et_scenario_t* const scenario)
{
  et_event_t        event;
  et_display_scenario(scenario);

  // create SCTP ITTI task: same as eNB code
  if (itti_create_task (TASK_SCTP, sctp_eNB_task, NULL) < 0) {
    LOG_E(SCTP, "Create task for SCTP failed\n");
    return -1;
  }

  // create S1AP ITTI task: not as same as eNB code
  if (itti_create_task (TASK_S1AP, et_s1ap_eNB_task, NULL) < 0) {
    LOG_E(S1AP, "Create task for S1AP failed\n");
    return -1;
  }

  // create ENB_APP ITTI task: not as same as eNB code
  if (itti_create_task (TASK_ENB_APP, et_eNB_app_task, NULL) < 0) {
    LOG_E(ENB_APP, "Create task for ENB_APP failed\n");
    return -1;
  }

  event.code = ET_EVENT_INIT;
  event.u.init.scenario = scenario;
  et_scenario_fsm_notify_event(event);


  return 0;
}

//------------------------------------------------------------------------------
static void et_usage (
    int argc,
    char *argv[])
//------------------------------------------------------------------------------
{
  fprintf (stdout, "Please report any bug to: %s\n",PACKAGE_BUGREPORT);
  fprintf (stdout, "Usage: %s [options]\n\n", argv[0]);
  fprintf (stdout, "\n");
  fprintf (stdout, "Client options:\n");
  fprintf (stdout, "\t-S | --server         <server network @>  File name (with no path) of a test scenario that has to be replayed (TODO in future?)\n");
  fprintf (stdout, "Server options:\n");
  fprintf (stdout, "\t-d | --test-dir       <dir>               Directory where a set of files related to a particular test are located\n");
  fprintf (stdout, "\t-c | --enb-conf-file  <file>              Provide an eNB config file, valid for the testbed\n");
  fprintf (stdout, "\t-s | --scenario       <file>              File name (with no path) of a test scenario that has to be replayed ()\n");
  fprintf (stdout, "\n");
  fprintf (stdout, "Other options:\n");
  fprintf (stdout, "\t-h | --help                               Print this help and return\n");
  fprintf (stdout, "\t-v | --version                            Print informations about the version of this executable\n");
  fprintf (stdout, "\n");
}

//------------------------------------------------------------------------------
int
et_config_parse_opt_line (
  int argc,
  char *argv[],
  char **et_dir_name,
  char **scenario_file_name,
  char **enb_config_file_name)
//------------------------------------------------------------------------------
{
  int                           option;
  int                           rv                   = 0;
  const Enb_properties_array_t *enb_properties_p     = NULL;

  enum long_option_e {
    LONG_OPTION_START = 0x100, /* Start after regular single char options */
    LONG_OPTION_ENB_CONF_FILE,
    LONG_OPTION_SCENARIO_FILE,
    LONG_OPTION_TEST_DIR,
    LONG_OPTION_HELP,
    LONG_OPTION_VERSION
  };

  static struct option long_options[] = {
    {"enb-conf-file",  required_argument, 0, LONG_OPTION_ENB_CONF_FILE},
    {"scenario ",      required_argument, 0, LONG_OPTION_SCENARIO_FILE},
    {"test-dir",       required_argument, 0, LONG_OPTION_TEST_DIR},
    {"help",           no_argument,       0, LONG_OPTION_HELP},
    {"version",        no_argument,       0, LONG_OPTION_VERSION},
     {NULL, 0, NULL, 0}
  };

  /*
   * Parsing command line
   */
  while ((option = getopt_long (argc, argv, "vhc:s:d:", long_options, NULL)) != -1) {
    switch (option) {
      case LONG_OPTION_ENB_CONF_FILE:
      case 'c':
        if (optarg) {
          *enb_config_file_name = strdup(optarg);
          printf("eNB config file name is %s\n", *enb_config_file_name);
          rv |= PLAY_SCENARIO;
        }
        break;

      case LONG_OPTION_SCENARIO_FILE:
      case 's':
        if (optarg) {
          *scenario_file_name = strdup(optarg);
          printf("Scenario file name is %s\n", *scenario_file_name);
          rv |= PLAY_SCENARIO;
        }
        break;

      case LONG_OPTION_TEST_DIR:
      case 'd':
        if (optarg) {
          *et_dir_name = strdup(optarg);
          if (is_file_exists(*et_dir_name, "test dirname") != GS_IS_DIR) {
            fprintf(stderr, "Please provide a valid test dirname, %s is not a valid directory name\n", *et_dir_name);
            exit(1);
          }
          printf("Test dir name is %s\n", *et_dir_name);
        }
        break;

      case LONG_OPTION_VERSION:
      case 'v':
        printf("Version %s\n", PACKAGE_VERSION);
        exit (0);
        break;

      case LONG_OPTION_HELP:
      case 'h':
      default:
        et_usage (argc, argv);
        exit (0);
    }
  }
  if (NULL == *et_dir_name) {
    fprintf(stderr, "Please provide a valid test dirname\n");
    exit(1);
  }
  if (chdir(*et_dir_name) != 0) {
    fprintf(stderr, "ERROR: chdir %s returned %s\n", *et_dir_name, strerror(errno));
    exit(1);
  }
  if (rv & PLAY_SCENARIO) {
    if (NULL == *enb_config_file_name) {
      fprintf(stderr, "ERROR: please provide the original eNB config file name that should be in %s\n", *et_dir_name);
    }
    if (is_file_exists(*enb_config_file_name, "eNB config file") != GS_IS_FILE) {
      fprintf(stderr, "ERROR: original eNB config file name %s is not found in dir %s\n", *enb_config_file_name, *et_dir_name);
    }
    enb_properties_p = enb_config_init(*enb_config_file_name);

    if (NULL == *scenario_file_name) {
      fprintf(stderr, "ERROR: please provide the scenario file name that should be in %s\n", *et_dir_name);
    }
    if (is_file_exists(*scenario_file_name, "Scenario file") != GS_IS_FILE) {
      fprintf(stderr, "ERROR: Scenario file name %s is not found in dir %s\n", *scenario_file_name, *et_dir_name);
    }
  }
  return rv;
}

//------------------------------------------------------------------------------
int main( int argc, char **argv )
//------------------------------------------------------------------------------
{
  int              actions              = 0;
  char            *et_dir_name          = NULL;
  char            *scenario_file_name   = NULL;
  char            *enb_config_file_name = NULL;
  int              ret                  = 0;
  et_scenario_t   *scenario             = NULL;
  char             play_scenario_filename[NAME_MAX];

  memset(play_scenario_filename, 0, sizeof(play_scenario_filename));
  g_openair_dir = getenv("OPENAIR_DIR");
  if (NULL == g_openair_dir) {
    fprintf(stderr, "ERROR: Could not get OPENAIR_DIR environment variable\n");
    exit(1);
  }

  // logging
  logInit();
  itti_init(TASK_MAX, THREAD_MAX, MESSAGES_ID_MAX, tasks_info, messages_info, messages_definition_xml, NULL);

  set_comp_log(S1AP, LOG_TRACE, LOG_MED, 1);
  set_comp_log(SCTP, LOG_TRACE, LOG_MED, 1);
  asn_debug      = 0;
  asn1_xer_print = 1;

  //parameters
  actions = et_config_parse_opt_line (argc, argv, &et_dir_name, &scenario_file_name, &enb_config_file_name); //Command-line options
  if  (actions & PLAY_SCENARIO) {
    if (et_generate_xml_scenario(et_dir_name, scenario_file_name,enb_config_file_name, play_scenario_filename) == 0) {
      if (NULL != (scenario = et_generate_scenario(play_scenario_filename))) {
        ret = et_play_scenario(scenario);
      } else {
        fprintf(stderr, "ERROR: Could not generate scenario from tsml file\n");
        ret = -1;
      }
    } else {
      fprintf(stderr, "ERROR: Could not generate tsml scenario from xml file\n");
      ret = -1;
    }
    et_free_pointer(et_dir_name);
    et_free_pointer(scenario_file_name);
    et_free_pointer(enb_config_file_name);
  }

  return ret;
}
