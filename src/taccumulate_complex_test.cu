#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif

#include <cuda_runtime.h>
#include <cuda.h>
#include <cufft.h>
#include <time.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <inttypes.h>
#include "cudautil.cuh"
#include "kernel.cuh"

#include "constants.h"

extern "C" void usage ()
{
  fprintf (stdout,
	   "taccumulate_complex_test - Test the accumulate kernel \n"
	   "\n"
	   "Usage: taccumulate_complex_test [options]\n"
	   " -a  Grid size in X\n"
	   " -b  Grid size in Y\n"
	   " -c  Block size in X\n"
	   " -h  show help\n");
}

// ./taccumulate_complex_test -a 512 -b 1 -c 512
int main(int argc, char *argv[])
{
  int i, j, arg;
  int grid_x, grid_y, block_x;
  uint64_t n_accumulate;
  uint64_t len_in, len_out, idx;
  dim3 gridsize_accumulate, blocksize_accumulate;
  float h_total = 0, g_total = 0;
  cufftComplex *h_result = NULL, *g_result = NULL, *data = NULL, *g_in = NULL, *g_out = NULL;
  
  /* Read in parameters, the arguments here have the same name  */
  while((arg=getopt(argc,argv,"a:b:hc:")) != -1)
    {
      switch(arg)
	{
	case 'h':
	  usage();
	  exit(EXIT_FAILURE);	  

	case 'a':	  
	  if (sscanf (optarg, "%d", &grid_x) != 1)
	    {
	      fprintf (stderr, "Does not get grid_x, which happens at \"%s\", line [%d].\n", __FILE__, __LINE__);
	      exit(EXIT_FAILURE);
	    }
	  break;
	  
	case 'b':	  
	  if (sscanf (optarg, "%d", &grid_y) != 1)
	    {
	      fprintf (stderr, "Does not get grid_y, which happens at \"%s\", line [%d].\n", __FILE__, __LINE__);
	      exit(EXIT_FAILURE);
	    }
	  break;
	  
	case 'c':	  
	  if (sscanf (optarg, "%d", &block_x) != 1)
	    {
	      fprintf (stderr, "Does not get block_x, which happens at \"%s\", line [%d].\n", __FILE__, __LINE__);
	      exit(EXIT_FAILURE);
	    }
	  break;
	}
    }
  n_accumulate = block_x * 2;
  fprintf(stdout, "grid_x is %d, grid_y is %d, block_x is %d and n_accumulate is %"SCNu64"\n", grid_x, grid_y, block_x, n_accumulate);
  
  /* Setup size */
  gridsize_accumulate.x  = grid_x;
  gridsize_accumulate.y  = grid_y;
  gridsize_accumulate.z  = 1;
  blocksize_accumulate.x = block_x;
  blocksize_accumulate.y = 1;
  blocksize_accumulate.z = 1;
  len_out                = grid_x*grid_y;
  len_in                 = len_out*n_accumulate;

  /* Create buffer */
  CudaSafeCall(cudaMallocHost((void **)&data,     len_in * NBYTE_CUFFT_COMPLEX));
  CudaSafeCall(cudaMallocHost((void **)&h_result, len_out * NBYTE_CUFFT_COMPLEX));
  CudaSafeCall(cudaMallocHost((void **)&g_result, len_out * NBYTE_CUFFT_COMPLEX));
  CudaSafeCall(cudaMalloc((void **)&g_in,         len_in * NBYTE_CUFFT_COMPLEX));
  CudaSafeCall(cudaMalloc((void **)&g_out,        len_out * NBYTE_CUFFT_COMPLEX));

  /* cauculate on CPU */
  srand(time(NULL));
  for(i = 0; i < len_out; i ++)
    {
      h_result[i].x = 0;
      h_result[i].y = 0;
      for(j = 0; j < n_accumulate; j++)
	{
	  idx = i * n_accumulate + j;
	  data[idx].x = rand()*RAND_STD/RAND_MAX;
	  data[idx].y = rand()*RAND_STD/RAND_MAX;

	  h_result[i].x += data[idx].x;
	  h_result[i].y += data[idx].y;
	}
    }
  
  /* Calculate on GPU */
  CudaSafeCall(cudaMemcpy(g_in, data, len_in * NBYTE_CUFFT_COMPLEX, cudaMemcpyHostToDevice));
  taccumulate_complex_kernel<<<gridsize_accumulate, blocksize_accumulate, blocksize_accumulate.x * NBYTE_CUFFT_COMPLEX>>>(g_in, g_out);
  CudaSafeKernelLaunch();

  CudaSafeCall(cudaMemcpy(g_result, g_out, len_out * NBYTE_CUFFT_COMPLEX, cudaMemcpyDeviceToHost));

  /* Check the result */
  for(i = 0; i < len_out; i++)
    {
      h_total += (h_result[i].x + h_result[i].y);
      g_total += (g_result[i].x + g_result[i].y);
    }
  //fprintf(stdout, "%f\t%f\t%E\n", h_total, g_total, (g_total - h_total)/h_total);
  fprintf(stdout, "CPU:\t%f\nGPU:\t%f\n%E\n", h_total, g_total, (g_total - h_total)/h_total);
  
  /* Free buffer */
  CudaSafeCall(cudaFreeHost(data));
  CudaSafeCall(cudaFreeHost(h_result));
  CudaSafeCall(cudaFreeHost(g_result));
  CudaSafeCall(cudaFree(g_in));
  CudaSafeCall(cudaFree(g_out));
  
  return EXIT_SUCCESS;
}