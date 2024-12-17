#! /usr/bin/env python

from __future__ import print_function
import sys
from optparse import OptionParser
import random

# Function to set the random seed for consistent results across runs
def random_seed(seed):
    try:
        random.seed(seed, version=1)  # For Python >= 3.2
    except:
        random.seed(seed)  # Fallback for older Python versions
    return

# Class to simulate an Operating System (OS) with multi-level page tables
class OS:
    def __init__(self, levels=3):
        # Configuration for virtual memory and physical memory
        self.levels = levels  # Number of levels in the page table (1, 2, or 3)

        # Physical memory configuration: 4k memory with 128 pages
        self.pageSize = 32  # Each page has 32 bytes
        self.physPages = 128  # Total physical pages
        self.physMem = self.pageSize * self.physPages  # Total physical memory size in bytes

        # Virtual memory space configuration
        self.vaPages = 1024  # Virtual memory has 1024 pages
        self.vaSize = self.pageSize * self.vaPages  # Total virtual memory size
        self.pteSize = 1  # Page Table Entry size
        self.pageBits = 5  # log2(pageSize) = 5 bits for offset

        # Masks and bit shifts for multi-level page tables
        self.L0_MASK = 0xF800  # Mask for Level 0 directory
        self.L0_SHIFT = 15  # Shift bits for Level 0 directory
        self.PDE_MASK = 0x07C0  # Mask for Level 1 directory
        self.PDE_SHIFT = 10  # Shift bits for Level 1 directory
        self.PTE_MASK = 0x003E  # Mask for Level 2 page table
        self.PTE_SHIFT = 5  # Shift bits for Level 2 page table
        self.OFFSET_MASK = 0x001F  # Mask for byte offset within a page

        # Data structures to track memory and page tables
        self.usedPages = [0] * self.physPages  # Tracks allocated physical pages
        self.memory = [0] * self.physMem  # Simulates the physical memory
        self.pdbr = {}  # Page Directory Base Register (maps process IDs to page directories)

    # Function to find a free physical page
    def findFree(self):
        freePage = random.choice([i for i in range(self.physPages) if self.usedPages[i] == 0])
        self.usedPages[freePage] = 1  # Mark page as used
        return freePage

    # Function to initialize a page directory by setting all entries to invalid (0x7F)
    def initPageDir(self, whichPage):
        whichByte = whichPage << self.pageBits  # Calculate the starting byte of the page
        for i in range(whichByte, whichByte + self.pageSize):
            self.memory[i] = 0x7F  # Set all entries to invalid (0x7F)

    # Function to translate a virtual address to a physical address
    def translate(self, pid, virtualAddr):
        if self.levels >= 3:
            # Level 0 Page Directory Lookup
            level0Bits = (virtualAddr & self.L0_MASK) >> self.L0_SHIFT
            l0Addr = self.pdbr[pid] << self.pageBits  # Get Level 0 base address
            l0Entry = self.memory[l0Addr + level0Bits]  # Fetch entry from Level 0
            l0Valid = (l0Entry & 0x80) >> 7  # Check valid bit
            l1Ptr = l0Entry & 0x7F  # Get Level 1 pointer

            if l0Valid != 1:
                return -3  # Fault at Level 0

        if self.levels >= 2:
            # Level 1 Directory Lookup
            l1Bits = (virtualAddr & self.PDE_MASK) >> self.PDE_SHIFT
            l1Addr = ((l1Ptr if self.levels == 3 else self.pdbr[pid]) << self.pageBits) + l1Bits
            l1Entry = self.memory[l1Addr]  # Fetch Level 1 entry
            l1Valid = (l1Entry & 0x80) >> 7  # Check valid bit
            l2Ptr = l1Entry & 0x7F  # Get Level 2 pointer

            if l1Valid != 1:
                return -2  # Fault at Level 1

        # Level 2 Page Table Lookup
        l2Bits = (virtualAddr & self.PTE_MASK) >> self.PTE_SHIFT
        l2Addr = ((l2Ptr if self.levels >= 2 else self.pdbr[pid]) << self.pageBits) + l2Bits
        l2Entry = self.memory[l2Addr]  # Fetch Level 2 entry
        l2Valid = (l2Entry & 0x80) >> 7  # Check valid bit
        pfn = l2Entry & 0x7F  # Get Physical Frame Number

        if l2Valid != 1:
            return -1  # Fault at Level 2

        # Calculate final physical address using the page frame and offset
        offset = virtualAddr & self.OFFSET_MASK
        return (pfn << self.pageBits) | offset

    # Function to allocate a virtual page for a process
    def allocVirtualPage(self, pid, virtualPage, physicalPage):
        # Level 0 Page Directory Allocation
        if self.levels >= 3:
            l0Addr = self.pdbr[pid] << self.pageBits
            l0Index = (virtualPage & self.L0_MASK) >> self.L0_SHIFT
            l0Entry = self.memory[l0Addr + l0Index]

            if (l0Entry & 0x80) == 0:  # If not valid
                l1Page = self.findFree()  # Allocate Level 1 page
                self.memory[l0Addr + l0Index] = 0x80 | l1Page  # Mark valid and assign page
                self.initPageDir(l1Page)
            else:
                l1Page = l0Entry & 0x7F

        # Level 1 Directory Allocation
        l1Addr = ((l1Page if self.levels == 3 else self.pdbr[pid]) << self.pageBits) + ((virtualPage & self.PDE_MASK) >> self.PDE_SHIFT)
        l1Entry = self.memory[l1Addr]

        if (l1Entry & 0x80) == 0:
            l2Page = self.findFree()  # Allocate Level 2 page
            self.memory[l1Addr] = 0x80 | l2Page
            self.initPageDir(l2Page)
        else:
            l2Page = l1Entry & 0x7F

        # Level 2 Page Table Allocation
        l2Addr = (l2Page << self.pageBits) + ((virtualPage & self.PTE_MASK) >> self.PTE_SHIFT)
        if (self.memory[l2Addr] & 0x80) == 0:  # If not already valid
            self.memory[l2Addr] = 0x80 | physicalPage

    # Function to allocate virtual pages for a process
    def procAlloc(self, pid, numPages):
        pageDir = self.findFree()
        self.pdbr[pid] = pageDir
        self.initPageDir(pageDir)

        allocatedVPs = set()
        for _ in range(numPages):
            vp = random.randint(0, self.vaPages - 1)
            while vp in allocatedVPs:
                vp = random.randint(0, self.vaPages - 1)
            pp = self.findFree()
            self.allocVirtualPage(pid, vp, pp)
            allocatedVPs.add(vp)
        return list(allocatedVPs)

    # Function to dump physical memory for debugging
    def memoryDump(self):
        for i in range(self.physPages):
            print(f"Page {i:03}: {''.join(f'{b:02x}' for b in self.memory[i * self.pageSize:(i + 1) * self.pageSize])}")

# Main Program to parse options and simulate virtual address translation
parser = OptionParser()
parser.add_option('-s', '--seed', default=0, help='the random seed', action='store', type='int', dest='seed')
parser.add_option('-a', '--allocated', default=64, help='number of virtual pages allocated', action='store', type='int', dest='allocated')
parser.add_option('-n', '--addresses', default=10, help='number of virtual addresses to generate', action='store', type='int', dest='num')
parser.add_option('-c', '--solve', help='compute answers for me', action='store_true', default=False, dest='solve')

(options, args) = parser.parse_args()
random_seed(options.seed)

# Initialize the OS and allocate virtual pages
os = OS(levels=3)
used = os.procAlloc(1, options.allocated)

# Print the physical memory dump
os.memoryDump()
print('\nPDBR:', os.pdbr[1], ' (decimal)\n')

# Generate and translate virtual addresses
for i in range(options.num):
    vaddr = random.randint(0, os.vaSize - 1)
    if options.solve:
        print(f'Virtual Address 0x{vaddr:04x}:')
        result = os.translate(1, vaddr)
        if result >= 0:
            print(f'  --> Physical Address 0x{result:03x}')
        else:
            print(f'  --> Fault at Level {-result}')
    else:
        print(f'Virtual Address 0x{vaddr:04x}: Translates to Physical Address or Fault?')
